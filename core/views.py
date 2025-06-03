from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.contrib import messages
from .models import *
from .forms import *
from datetime import date, timedelta, datetime
from django.urls import reverse
from django.http import JsonResponse
import logging
from accounts.models import TaiKhoan
import json
from django.utils import timezone
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.db import transaction

logger = logging.getLogger(__name__)
timeout = settings.SESSION_COOKIE_AGE

# Role-based access control functions
def is_admin(user):
    try:
        return user.is_authenticated and (user.is_superuser or getattr(user, 'loai_tk', '').strip().lower() == 'admin')
    except AttributeError as e:
        logger.error(f"Error in is_admin: {str(e)}")
        return False

def is_staff(user):
    try:
        return user.is_authenticated and getattr(user, 'loai_tk', '').strip().lower() == 'nhan_vien'
    except AttributeError as e:
        logger.error(f"Error in is_staff: {str(e)}")
        return False

def is_customer(user):
    try:
        return user.is_authenticated and getattr(user, 'loai_tk', '').strip().lower() == 'khach_hang' and hasattr(user, 'khachhang')
    except AttributeError as e:
        logger.error(f"Error in is_customer: {str(e)}")
        return False

def is_admin_or_staff(user):
    return is_admin(user) or is_staff(user)

# ------------------- General Views (Accessible to All or Unauthenticated) -------------------

def home(request):
    logger.debug(f"Home view accessed by user: {request.user.username if request.user.is_authenticated else 'Anonymous'}, Authenticated: {request.user.is_authenticated}")
    featured_rooms = Phong.objects.filter(trang_thai='trong')[:8]
    services = DichVu.objects.filter(hoat_dong=True)[:3]

    total_customers = KhachHang.objects.count()
    total_bookings = DonDatPhong.objects.count()
    total_rooms = Phong.objects.count()

    if request.method == 'POST' and 'search_rooms' in request.POST:
        check_in = request.POST.get('check_in')
        check_out = request.POST.get('check_out')
        guests = request.POST.get('guests', 1)
        room_type = request.POST.get('room_type', '')

        return redirect(
            'room_search') + f'?check_in={check_in}&check_out={check_out}&guests={guests}&room_type={room_type}'

    context = {
        'featured_rooms': featured_rooms,
        'services': services,
        'total_customers': total_customers,
        'total_bookings': total_bookings,
        'total_rooms': total_rooms,
    }
    return render(request, 'core/home.html', context)

def room_search(request):
    room_status = request.GET.get('room_status', 'trong')
    guests_str = request.GET.get('guests', '1')
    room_type = request.GET.get('room_type', '')

    rooms = Phong.objects.all()

    if room_status:
        rooms = rooms.filter(trang_thai=room_status)

    if guests_str:
        try:
            guests_int = int(guests_str)
            rooms = rooms.filter(suc_chua__gte=guests_int)
        except ValueError:
            pass

    if room_type:
        rooms = rooms.filter(loai_p=room_type)

    context = {
        'rooms': rooms,
        'room_status': room_status,
        'guests': guests_str,
        'room_type': room_type,
    }
    return render(request, 'core/room_search.html', context)

def service_list(request):
    search_query = request.GET.get('search', '')

    services_qs = DichVu.objects.filter(hoat_dong=True)

    if search_query:
        services_qs = services_qs.filter(
            Q(ten_dv__icontains=search_query) |
            Q(mo_ta__icontains=search_query) |
            Q(ma_dv__icontains=search_query)
        )

    paginator = Paginator(services_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    return render(request, 'core/service_list.html', context)

def service_detail(request, pk):
    service = get_object_or_404(DichVu, pk=pk)
    context = {
        'service': service,
    }
    return render(request, 'core/service_detail.html', context)

@method_decorator(csrf_exempt, name='dispatch')
class RoomDetailView(View):
    def get(self, request, pk):
        room = get_object_or_404(Phong, pk=pk)
        additional_images = room.anh_phu.all()

        all_room_images = []
        if room.anh_dai_dien:
            all_room_images.append({'url': room.anh_dai_dien.url, 'alt': room.ten_p + " - Ảnh đại diện"})

        for img in additional_images:
            all_room_images.append({'url': img.anh.url, 'alt': img.mo_ta_anh or f"Ảnh thêm của {room.ten_p}"})

        available_services = DichVu.objects.filter(hoat_dong=True).order_by('ten_dv')

        context = {
            'room': room,
            'all_room_images': all_room_images,
            'additional_images': additional_images,
            'available_services': available_services,
            'booking_success': False,
        }
        return render(request, 'core/room_detail.html', context)

    def post(self, request, pk):
        room = get_object_or_404(Phong, pk=pk)
        step = request.POST.get('step', '1')

        if not request.session.session_key:
            request.session.create()
            logger.debug(f"Created new session: {request.session.session_key}")

        if step == '1':
            try:
                check_in_str = request.POST.get('check_in')
                check_out_str = request.POST.get('check_out')
                guests_str = request.POST.get('guests', '1')
                selected_services_json = request.POST.get('selected_services_json', '[]')

                if not check_in_str or not check_out_str:
                    return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập đầy đủ ngày nhận và trả phòng.'}, status=400)

                date_in = datetime.strptime(check_in_str, '%Y-%m-%d').date()
                if date_in < timezone.now().date():
                    return JsonResponse({'status': 'error', 'message': 'Ngày nhận phòng không được chọn trong quá khứ.'}, status=400)

                date_out = datetime.strptime(check_out_str, '%Y-%m-%d').date()
                if date_out <= date_in:
                    return JsonResponse({'status': 'error', 'message': 'Ngày trả phòng phải sau ngày nhận phòng.'}, status=400)

                try:
                    selected_service_ids = json.loads(selected_services_json)
                    if not isinstance(selected_service_ids, list):
                        selected_service_ids = []
                except json.JSONDecodeError:
                    selected_service_ids = []

                request.session['booking_data'] = {
                    'check_in': check_in_str,
                    'check_out': check_out_str,
                    'guests': guests_str,
                    'room_id': pk,
                    'selected_service_ids': selected_service_ids,
                    'timestamp': str(timezone.now())
                }
                request.session.modified = True
                logger.debug(f"Session saved (step 1): {request.session['booking_data']}")
                return JsonResponse({'status': 'success', 'message': 'Thông tin lưu trú đã được lưu tạm.'})

            except ValueError as e:
                logger.error(f"ValueError in step 1: {e}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'Ngày không hợp lệ hoặc định dạng sai.'}, status=400)
            except Exception as e:
                logger.error(f"Exception in step 1: {e}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'Lỗi không xác định ở bước 1.'}, status=500)

        elif step == '2':
            if 'booking_data' not in request.session:
                logger.error(f"Session data missing for step 2. Session keys: {list(request.session.keys())}")
                return JsonResponse({'status': 'error', 'message': 'Phiên làm việc hết hạn hoặc dữ liệu tạm thời không tồn tại. Vui lòng thử lại.'}, status=419)

            try:
                booking_data = request.session['booking_data']
                logger.debug(f"Retrieved booking data (step 2): {booking_data}")

                if str(booking_data.get('room_id')) != str(pk):
                    logger.error(f"Room ID mismatch. Session: {booking_data.get('room_id')}, URL PK: {pk}")
                    return JsonResponse({'status': 'error', 'message': 'Lỗi: Thông tin phòng không khớp.'}, status=400)

                check_in_str = booking_data['check_in']
                check_out_str = booking_data['check_out']
                guests = int(booking_data['guests'])
                selected_service_ids = booking_data.get('selected_service_ids', [])

                if not request.user.is_authenticated:
                    return JsonResponse({'status': 'error', 'message': 'Vui lòng đăng nhập để hoàn tất đặt phòng.'}, status=401)

                khach_hang_profile = getattr(request.user, 'khachhang', None)
                if not khach_hang_profile:
                    logger.warning(f"User {request.user.username} does not have KhachHang profile.")
                    return JsonResponse({'status': 'error', 'message': 'Không tìm thấy thông tin khách hàng. Vui lòng cập nhật hồ sơ của bạn.'}, status=400)

                date_in = datetime.strptime(check_in_str, '%Y-%m-%d').date()
                date_out = datetime.strptime(check_out_str, '%Y-%m-%d').date()

                if date_in < timezone.now().date():
                    return JsonResponse({'status': 'error', 'message': 'Ngày nhận phòng không được chọn trong quá khứ.'}, status=400)
                if date_out <= date_in:
                    return JsonResponse({'status': 'error', 'message': 'Ngày trả phòng phải sau ngày nhận phòng.'}, status=400)
                if guests > room.suc_chua:
                    return JsonResponse({'status': 'error', 'message': f"Số lượng khách vượt quá sức chứa ({room.suc_chua} người) của phòng."}, status=400)

                conflicting_bookings = DonDatPhong.objects.filter(
                    phong=room,
                    ngay_nhan__lt=date_out,
                    ngay_tra__gt=date_in,
                    trang_thai__in=['da_xac_nhan', 'da_checkin']
                ).exists()

                if conflicting_bookings:
                    return JsonResponse({'status': 'error', 'message': 'Rất tiếc, phòng này vừa có người khác đặt trong khoảng thời gian bạn chọn. Vui lòng chọn lại.'}, status=409)

                days = (date_out - date_in).days
                if days <= 0:
                    return JsonResponse({'status': 'error', 'message': 'Số ngày đặt phòng phải lớn hơn 0.'}, status=400)

                with transaction.atomic():
                    booking = DonDatPhong.objects.create(
                        phong=room,
                        ngay_nhan=date_in,
                        ngay_tra=date_out,
                        so_luong_nguoi=guests,
                        khach_hang=khach_hang_profile,
                        gia_ddp=room.gia * days,
                        trang_thai='cho_xac_nhan'
                    )

                    if selected_service_ids:
                        default_service_date = date_in
                        default_service_time = datetime.now().time()

                        for service_id_str in selected_service_ids:
                            try:
                                service_id = int(service_id_str)
                                service_instance = DichVu.objects.get(pk=service_id, hoat_dong=True)
                                DonDatDichVu.objects.create(
                                    don_dat_phong=booking,
                                    dich_vu=service_instance,
                                    ngay_su_dung=default_service_date,
                                    gio_su_dung=default_service_time,
                                    so_luong=1,
                                    thanh_tien=service_instance.phi_dv
                                )
                            except DichVu.DoesNotExist:
                                logger.warning(f"Service with id {service_id_str} not found or not active. Skipping.")
                            except ValueError:
                                logger.warning(f"Invalid service id format: {service_id_str}. Skipping.")

                if 'booking_data' in request.session:
                    del request.session['booking_data']
                    request.session.modified = True

                logger.info(f"Booking #{booking.ma_ddp} created successfully for room {room.ten_p} by {request.user.username}")
                return JsonResponse({
                    'status': 'success',
                    'message': 'Đặt phòng và dịch vụ thành công!',
                    'redirect_url': reverse('booking_detail', args=[booking.ma_ddp])
                })

            except KhachHang.DoesNotExist:
                logger.error(f"KhachHang profile not found for user {request.user.username} during step 2.", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy thông tin khách hàng liên kết với tài khoản này.'}, status=400)
            except Exception as e:
                logger.error(f"Booking error step 2: {str(e)}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'Đã có lỗi xảy ra trong quá trình đặt phòng. Vui lòng thử lại.'}, status=500)

        else:
            return JsonResponse({'status': 'error', 'message': 'Bước xử lý không hợp lệ.'}, status=400)

# ------------------- Admin Views (Admin Only) -------------------

# Cho phép cả admin và nhân viên xem danh sách phòng
@login_required
@user_passes_test(is_admin_or_staff)
def admin_room_management(request):
    logger.debug(f"User accessing admin_room_management: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    rooms = Phong.objects.all().order_by('ma_p')

    search_query = request.GET.get('search', '')
    room_type = request.GET.get('type', '')
    status = request.GET.get('status', '')

    if search_query:
        rooms = rooms.filter(Q(ten_p__icontains=search_query) | Q(mo_ta__icontains=search_query))

    if room_type:
        rooms = rooms.filter(loai_p=room_type)

    if status:
        rooms = rooms.filter(trang_thai=status)

    paginator = Paginator(rooms, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Chỉ admin được thêm phòng
    form = None
    if request.user.loai_tk == 'admin':
        form = PhongForm(request.POST or None, request.FILES or None)
        if request.method == 'POST' and form.is_valid():
            form.save()
            messages.success(request, "Đã thêm phòng mới")
            return redirect('admin_room_management')

    context = {
        'page_obj': page_obj,
        'form': form,
        'search_query': search_query,
        'room_type': room_type,
        'status': status,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
    }
    return render(request, 'admin/room_management.html', context)

# Chỉ admin được chỉnh sửa phòng
@login_required
@user_passes_test(is_admin_or_staff)
def edit_room(request, pk):
    logger.debug(f"User accessing edit_room: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    if not is_admin(request.user):
        messages.error(request, "Bạn không có quyền truy cập chức năng này.")
        return redirect('admin_room_management')

    room = get_object_or_404(Phong, pk=pk)

    if request.method == 'POST':
        form = PhongForm(request.POST, request.FILES, instance=room)
        formset = AnhPhongFormSet(request.POST, request.FILES, instance=room, prefix='anhphu')

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Đã cập nhật thông tin phòng và ảnh.")
            return redirect('admin_room_management')
        else:
            messages.error(request, "Vui lòng kiểm tra lại thông tin phòng và ảnh.")
    else:
        form = PhongForm(instance=room)
        formset = AnhPhongFormSet(instance=room, prefix='anhphu')

    context = {
        'form': form,
        'formset': formset,
        'room': room,
    }
    return render(request, 'admin/edit_room.html', context)

# Chỉ admin được xóa phòng
@login_required
@user_passes_test(is_admin_or_staff)
def delete_room(request, pk):
    logger.debug(f"User accessing delete_room: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    if not is_admin(request.user):
        messages.error(request, "Bạn không có quyền truy cập chức năng này.")
        return redirect('admin_room_management')

    room = get_object_or_404(Phong, pk=pk)

    if request.method == 'POST':
        room.delete()
        messages.success(request, "Đã xóa phòng")
        return redirect('admin_room_management')

    context = {
        'room': room,
    }
    return render(request, 'admin/delete_room.html', context)

# Cho phép cả admin và nhân viên xem danh sách khách hàng
@login_required
@user_passes_test(is_admin_or_staff)
def admin_customer_management(request):
    logger.debug(f"User accessing admin_customer_management: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    customers = KhachHang.objects.all().order_by('-ma_kh')

    search_query = request.GET.get('search', '')
    if search_query:
        customers = customers.filter(
            Q(ten_kh__icontains=search_query) |
            Q(sdt__icontains=search_query) |
            Q(email__icontains=search_query))

    paginator = Paginator(customers, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
    }
    return render(request, 'admin/customer_management.html', context)

# Cho phép cả admin và nhân viên xem chi tiết khách hàng
@login_required
@user_passes_test(is_admin_or_staff)
def customer_detail(request, pk):
    logger.debug(f"User accessing customer_detail: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    customer = get_object_or_404(KhachHang, pk=pk)
    bookings = DonDatPhong.objects.filter(khach_hang=customer).order_by('-ngay_dat')

    context = {
        'customer': customer,
        'bookings': bookings,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
    }
    return render(request, 'admin/customer_detail.html', context)

# Chỉ admin được chỉnh sửa khách hàng
@login_required
@user_passes_test(is_admin_or_staff)
def edit_customer(request, pk):
    logger.debug(f"User accessing edit_customer: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    if not is_admin(request.user):
        messages.error(request, "Bạn không có quyền truy cập chức năng này.")
        return redirect('customer_detail', pk=pk)

    customer = get_object_or_404(KhachHang, pk=pk)

    if request.method == 'POST':
        form = KhachHangForm(request.POST, request.FILES, instance=customer)
        if form.is_valid():
            customer = form.save(commit=False)
            is_active_str = request.POST.get('is_active')
            customer.tai_khoan.is_active = (is_active_str == 'on')

            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            password_changed = False
            if new_password:
                if new_password != confirm_password:
                    messages.error(request, "Mật khẩu mới và xác nhận mật khẩu không khớp.")
                elif len(new_password) < 8:
                    messages.error(request, "Mật khẩu mới phải có ít nhất 8 ký tự.")
                else:
                    customer.tai_khoan.set_password(new_password)
                    password_changed = True

            customer.tai_khoan.save()
            customer.save()

            if password_changed:
                messages.success(request, "Đã cập nhật thông tin khách hàng và mật khẩu.")
            else:
                messages.success(request, "Đã cập nhật thông tin khách hàng.")
            return redirect('customer_detail', pk=pk)
        else:
            messages.error(request, "Vui lòng kiểm tra lại thông tin khách hàng.")
    else:
        form = KhachHangForm(instance=customer)

    context = {
        'form': form,
        'customer': customer,
    }
    return render(request, 'admin/edit_customer.html', context)

# Chỉ admin được xóa khách hàng
@login_required
@user_passes_test(is_admin_or_staff)
def delete_customer(request, pk):
    logger.debug(f"User accessing delete_customer: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    if not is_admin(request.user):
        messages.error(request, "Bạn không có quyền truy cập chức năng này.")
        return redirect('customer_detail', pk=pk)

    customer = get_object_or_404(KhachHang, pk=pk)

    if request.method == 'POST':
        user_account = customer.tai_khoan
        try:
            customer.delete()
            if user_account:
                user_account.delete()
            messages.success(request, f"Đã xóa khách hàng {customer.ten_kh} và tài khoản liên quan thành công.")
            return redirect('admin_customer_management')
        except Exception as e:
            messages.error(request, f"Không thể xóa khách hàng. Lỗi: {str(e)}")
            return redirect('customer_detail', pk=pk)

    return redirect('customer_detail', pk=pk)

# Chỉ admin được truy cập quản lý nhân viên
@login_required
@user_passes_test(is_admin)
def admin_staff_management(request):
    logger.debug(f"User accessing admin_staff_management: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    staff = NhanVien.objects.all().order_by('-ma_nv')

    search_query = request.GET.get('search', '')
    position = request.GET.get('position', '')
    status = request.GET.get('status', '')

    if search_query:
        staff = staff.filter(
            Q(ten_nv__icontains=search_query) |
            Q(sdt__icontains=search_query) |
            Q(email__icontains=search_query))

    if position:
        staff = staff.filter(vi_tri=position)

    if status:
        staff = staff.filter(trang_thai=status)

    paginator = Paginator(staff, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    form = NhanVienForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Đã thêm nhân viên mới")
        return redirect('admin_staff_management')

    context = {
        'page_obj': page_obj,
        'form': form,
        'search_query': search_query,
        'position': position,
        'status': status,
    }
    return render(request, 'admin/staff_management.html', context)

@login_required
@user_passes_test(is_admin)
def edit_staff(request, pk):
    staff = get_object_or_404(NhanVien, pk=pk)

    if request.method == 'POST':
        form = EditNhanVienForm(request.POST, request.FILES, instance=staff)
        if form.is_valid():
            try:
                staff = form.save()
                new_password = request.POST.get('new_password')
                if new_password:
                    if len(new_password) < 8:
                        messages.error(request, "Mật khẩu phải có ít nhất 8 ký tự")
                    else:
                        staff.tai_khoan.set_password(new_password)
                        staff.tai_khoan.save()
                        messages.success(request, "Đã cập nhật mật khẩu")
                messages.success(request, "Đã cập nhật thông tin nhân viên")
                return redirect('admin_staff_management')
            except Exception as e:
                messages.error(request, f"Có lỗi xảy ra: {str(e)}")
        else:
            messages.error(request, "Vui lòng kiểm tra lại thông tin")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = EditNhanVienForm(instance=staff)

    context = {
        'form': form,
        'staff': staff,
    }
    return render(request, 'admin/edit_staff.html', context)

@login_required
@user_passes_test(is_admin)
def delete_staff(request, pk):
    staff = get_object_or_404(NhanVien, pk=pk)

    if request.method == 'POST':
        staff.delete()
        messages.success(request, "Đã xóa nhân viên")
        return redirect('admin_staff_management')

    return render(request, 'admin/delete_staff.html', {'staff': staff})

# Cho phép cả admin và nhân viên xem danh sách dịch vụ
@login_required
@user_passes_test(is_admin_or_staff)
def admin_service_management(request):
    logger.debug(f"User accessing admin_service_management: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    services = DichVu.objects.all().order_by('-ma_dv')

    search_query = request.GET.get('search', '')
    status = request.GET.get('status', '')
    min_price_str = request.GET.get('min_price', '')
    max_price_str = request.GET.get('max_price', '')

    if search_query:
        services = services.filter(
            Q(ten_dv__icontains=search_query) |
            Q(mo_ta__icontains=search_query))

    if status == 'active':
        services = services.filter(hoat_dong=True)
    elif status == 'inactive':
        services = services.filter(hoat_dong=False)

    if min_price_str:
        try:
            services = services.filter(phi_dv__gte=float(min_price_str))
        except ValueError:
            pass

    if max_price_str:
        try:
            services = services.filter(phi_dv__lte=float(max_price_str))
        except ValueError:
            pass

    paginator = Paginator(services, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Chỉ admin được thêm dịch vụ
    form = None
    if request.user.loai_tk == 'admin':
        form = DichVuForm(request.POST or None, request.FILES or None)
        if request.method == 'POST' and form.is_valid():
            form.save()
            messages.success(request, "Đã thêm dịch vụ mới")
            return redirect('admin_service_management')

    context = {
        'page_obj': page_obj,
        'form': form,
        'search_query': search_query,
        'status': status,
        'min_price': min_price_str,
        'max_price': max_price_str,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
    }
    return render(request, 'admin/service_management.html', context)

# Chỉ admin được chỉnh sửa dịch vụ
@login_required
@user_passes_test(is_admin_or_staff)
def edit_service(request, pk):
    logger.debug(f"User accessing edit_service: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    if not is_admin(request.user):
        messages.error(request, "Bạn không có quyền truy cập chức năng này.")
        return redirect('admin_service_management')

    service = get_object_or_404(DichVu, pk=pk)

    if request.method == 'POST':
        form = DichVuForm(request.POST, request.FILES, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, "Đã cập nhật dịch vụ")
            return redirect('admin_service_management')
    else:
        form = DichVuForm(instance=service)

    context = {
        'form': form,
        'service': service,
    }
    return render(request, 'admin/edit_service.html', context)

# Chỉ admin được xóa dịch vụ
@login_required
@user_passes_test(is_admin_or_staff)
def delete_service(request, pk):
    logger.debug(f"User accessing delete_service: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    if not is_admin(request.user):
        messages.error(request, "Bạn không có quyền truy cập chức năng này.")
        return redirect('admin_service_management')

    service = get_object_or_404(DichVu, pk=pk)

    if request.method == 'POST':
        service.delete()
        messages.success(request, "Đã xóa dịch vụ")
        return redirect('admin_service_management')

    context = {
        'service': service,
    }
    return render(request, 'admin/delete_service.html', context)

@login_required
@user_passes_test(is_admin)
def add_room(request):
    if request.method == 'POST':
        form = PhongForm(request.POST, request.FILES)
        formset = AnhPhongFormSet(request.POST, request.FILES, prefix='anhphu')

        if form.is_valid() and formset.is_valid():
            phong_instance = form.save()
            formset.instance = phong_instance
            formset.save()
            messages.success(request, "Đã thêm phòng mới và các ảnh liên quan.")
            return redirect('admin_room_management')
        else:
            error_messages = []
            for field, errors in form.errors.items():
                for error in errors:
                    error_messages.append(f"Lỗi phòng - {form.fields[field].label if field in form.fields else field}: {error}")
            for i, f_err in enumerate(formset.errors):
                if f_err:
                    for field, errors in f_err.items():
                        for error in errors:
                            error_messages.append(f"Lỗi ảnh phụ {i + 1} - {field}: {error}")
            if not error_messages:
                error_messages.append("Vui lòng kiểm tra lại thông tin phòng và ảnh.")
            messages.error(request, " ".join(error_messages))
    else:
        form = PhongForm()
        formset = AnhPhongFormSet(queryset=AnhPhong.objects.none(), prefix='anhphu')

    context = {
        'form': form,
        'formset': formset,
    }
    return render(request, 'admin/add_room.html', context)

@login_required
@user_passes_test(is_admin)
def add_service(request):
    form = DichVuForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Đã thêm dịch vụ mới")
        return redirect('admin_service_management')

    return render(request, 'admin/add_service.html', {'form': form})

@login_required
@user_passes_test(is_admin)
def add_staff(request):
    if request.method == 'POST':
        form = AddNhanVienForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                username = form.cleaned_data['username']
                password = form.cleaned_data['password']
                email = form.cleaned_data['email']

                if TaiKhoan.objects.filter(username=username).exists():
                    messages.error(request, f"Tên đăng nhập '{username}' đã tồn tại.")
                elif TaiKhoan.objects.filter(email=email).exists():
                    messages.error(request, f"Email '{email}' đã được sử dụng.")
                else:
                    user = TaiKhoan.objects.create_user(
                        username=username,
                        password=password,
                        loai_tk='nhan_vien',
                        email=email
                    )
                    staff = form.save(commit=False)
                    staff.tai_khoan = user
                    staff.save()
                    messages.success(request, "Đã thêm nhân viên mới thành công")
                    return redirect('admin_staff_management')
            except Exception as e:
                logger.error(f"Error adding staff: {str(e)}", exc_info=True)
                messages.error(request, f"Lỗi khi thêm nhân viên: {str(e)}")
        else:
            error_list = []
            for field, errors in form.errors.items():
                error_list.append(f"{field.capitalize()}: {', '.join(errors)}")
            messages.error(request, "Dữ liệu không hợp lệ. " + " ".join(error_list))
    else:
        form = AddNhanVienForm()

    return render(request, 'admin/add_staff.html', {'form': form})

@login_required
@user_passes_test(is_admin)
def delete_request(request, pk):
    yeu_cau = get_object_or_404(YeuCau, pk=pk)

    if request.method == 'POST':
        yeu_cau.delete()
        messages.success(request, f"Đã xóa yêu cầu #{pk} thành công.")
        return redirect('admin_request_management')

    return redirect('process_request', pk=pk)

# ------------------- Admin/Staff Shared Views (Admin and Staff with Restrictions) -------------------

@login_required
@user_passes_test(lambda u: u.is_authenticated and getattr(u, 'loai_tk', '').strip().lower() in ['admin', 'nhan_vien'])
def admin_dashboard(request):
    logger.debug(f"Admin dashboard accessed by user: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    logger.debug(f"Session ID: {request.session.session_key}, Expiry: {request.session.get_expiry_date()}")

    staff_profile = None
    if request.user.loai_tk == 'nhan_vien':
        try:
            staff_profile = NhanVien.objects.get(tai_khoan=request.user)
        except NhanVien.DoesNotExist:
            logger.error(f"Staff profile not found for user: {request.user.username}")
            messages.error(request, "Tài khoản không có thông tin nhân viên. Vui lòng liên hệ quản trị viên để cập nhật hồ sơ nhân viên.")
            staff_profile = None

    total_rooms = Phong.objects.count()
    total_bookings = DonDatPhong.objects.count()
    total_customers = KhachHang.objects.count()
    total_services = DichVu.objects.count()

    recent_bookings = DonDatPhong.objects.order_by('-ngay_dat')[:5]

    if request.user.loai_tk == 'nhan_vien':
        if staff_profile:
            pending_requests = YeuCau.objects.filter(
                Q(nhan_vien=staff_profile) | Q(nhan_vien__isnull=True),
                tinh_trang__in=['cho_phan_cong', 'da_phan_cong', 'dang_xu_ly']
            )[:5]
        else:
            pending_requests = YeuCau.objects.none()
    else:
        pending_requests = YeuCau.objects.filter(tinh_trang='cho_phan_cong')[:5]

    context = {
        'total_rooms': total_rooms,
        'total_bookings': total_bookings,
        'total_customers': total_customers,
        'total_services': total_services,
        'recent_bookings': recent_bookings,
        'pending_requests': pending_requests,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
        'staff_profile': staff_profile,
    }
    return render(request, 'admin/dashboard.html', context)

@login_required
@user_passes_test(lambda u: u.is_authenticated and getattr(u, 'loai_tk', '').strip().lower() in ['admin', 'nhan_vien'])
def admin_booking_management(request):
    logger.debug(f"User accessing admin_booking_management: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    bookings = DonDatPhong.objects.all().order_by('-ngay_dat')

    search_query = request.GET.get('search', '')
    status = request.GET.get('status', '')

    if search_query:
        bookings = bookings.filter(
            Q(khach_hang__ten_kh__icontains=search_query) |
            Q(phong__ten_p__icontains=search_query) |
            Q(ma_ddp=search_query)
        )
    if status:
        bookings = bookings.filter(trang_thai=status)

    paginator = Paginator(bookings, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'status': status,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
    }
    return render(request, 'admin/booking_management.html', context)

@login_required
@user_passes_test(lambda u: u.is_authenticated and getattr(u, 'loai_tk', '').strip().lower() in ['admin', 'nhan_vien'])
def process_booking(request, pk):
    logger.debug(f"User accessing process_booking: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    booking = get_object_or_404(DonDatPhong, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')
        note = request.POST.get('note', '')

        # Nhân viên chỉ được phép xác nhận đơn đặt phòng
        if request.user.loai_tk == 'nhan_vien':
            if action != 'confirm':
                messages.error(request, "Bạn không có quyền thực hiện hành động này.")
                logger.warning(f"Staff {request.user.username} attempted unauthorized action: {action}")
                return redirect('admin_booking_management')  # Changed from 'admin_booking_history'
            if booking.trang_thai != 'cho_xac_nhan':
                messages.error(request, "Đơn đặt phòng không ở trạng thái chờ xác nhận.")
                logger.warning(f"Staff {request.user.username} attempted to confirm booking {booking.ma_ddp} with invalid status: {booking.trang_thai}")
                return redirect('admin_booking_management')

        if action == 'confirm':
            booking.trang_thai = 'da_xac_nhan'
            booking.ghi_chu = note
            booking.save()
            messages.success(request, "Đã xác nhận đặt phòng")
            logger.info(f"Booking {booking.ma_ddp} confirmed by {request.user.username}")

        elif request.user.loai_tk == 'admin':
            if action == 'checkin':
                if booking.trang_thai != 'da_xac_nhan':
                    messages.error(request, "Đơn đặt phòng phải ở trạng thái đã xác nhận để check-in.")
                    logger.warning(f"Admin {request.user.username} attempted to check-in booking {booking.ma_ddp} with invalid status: {booking.trang_thai}")
                    return redirect('admin_booking_management')
                booking.trang_thai = 'da_checkin'
                if booking.phong:  # Ensure phong exists
                    booking.phong.trang_thai = 'dang_su_dung'
                    booking.phong.save()
                else:
                    logger.warning(f"Booking {booking.ma_ddp} has no associated room during check-in.")
                booking.ghi_chu = note
                booking.save()
                messages.success(request, "Đã check-in khách")
                logger.info(f"Booking {booking.ma_ddp} checked-in by {request.user.username}")

            elif action == 'checkout':
                if booking.trang_thai != 'da_checkin':
                    messages.error(request, "Đơn đặt phòng phải ở trạng thái đã check-in để check-out.")
                    logger.warning(f"Admin {request.user.username} attempted to check-out booking {booking.ma_ddp} with invalid status: {booking.trang_thai}")
                    return redirect('admin_booking_management')
                booking.trang_thai = 'da_checkout'
                if booking.phong:  # Ensure phong exists
                    booking.phong.trang_thai = 'trong'
                    booking.phong.save()
                else:
                    logger.warning(f"Booking {booking.ma_ddp} has no associated room during check-out.")
                booking.ghi_chu = note
                booking.save()

                room_cost = booking.gia_ddp if booking.gia_ddp is not None else 0
                services_cost_data = booking.dondatdichvu_set.aggregate(total_services=Sum('thanh_tien'))
                services_cost = services_cost_data['total_services'] if services_cost_data['total_services'] is not None else 0
                total_invoice_amount = room_cost + services_cost

                if not HoaDon.objects.filter(don_dat_phong=booking).exists():
                    HoaDon.objects.create(
                        don_dat_phong=booking,
                        tong_tien=total_invoice_amount,
                        da_thanh_toan=False
                    )
                    messages.success(request, f"Đã check-out khách cho đơn #{booking.ma_ddp} và tạo hóa đơn.")
                else:
                    messages.info(request, f"Đã check-out khách cho đơn #{booking.ma_ddp}. Hóa đơn đã tồn tại.")
                logger.info(f"Booking {booking.ma_ddp} checked-out by {request.user.username}, Invoice total: {total_invoice_amount}")

            elif action == 'cancel':
                if booking.trang_thai == 'da_checkout':
                    messages.error(request, "Không thể hủy đơn đã check-out.")
                    logger.warning(f"Admin {request.user.username} attempted to cancel booking {booking.ma_ddp} with status: {booking.trang_thai}")
                    return redirect('admin_booking_management')
                booking.trang_thai = 'da_huy'
                booking.ghi_chu = note
                booking.save()
                messages.success(request, "Đã hủy đặt phòng")
                logger.info(f"Booking {booking.ma_ddp} canceled by {request.user.username}")

            else:
                messages.error(request, "Hành động không hợp lệ.")
                logger.warning(f"Admin {request.user.username} attempted invalid action: {action}")
                return redirect('admin_booking_management')
        else:
            messages.error(request, "Bạn không có quyền thực hiện hành động này.")
            logger.warning(f"User {request.user.username} (role: {request.user.loai_tk}) attempted unauthorized action: {action}")
            return redirect('admin_booking_management')

        return redirect('admin_booking_management')

    context = {
        'booking': booking,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
    }
    return render(request, 'admin/process_booking.html', context)


@login_required
@user_passes_test(lambda u: u.is_authenticated and getattr(u, 'loai_tk', '').strip().lower() in ['admin', 'nhan_vien'])
def admin_schedule_management(request):
    logger.debug(
        f"User accessing admin_schedule_management: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    today = timezone.now().date()
    year = request.GET.get('year', today.year)
    month = request.GET.get('month', today.month)

    try:
        year = int(year)
        month = int(month)
        current_date = date(year, month, 1)
    except (ValueError, TypeError):
        current_date = today.replace(day=1)

    prev_month = (current_date.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (current_date.replace(day=28) + timedelta(days=4)).replace(day=1)

    first_day = current_date.replace(day=1)
    last_day = (current_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    weeks = []
    week = []

    start_weekday = first_day.weekday()
    if start_weekday > 0:
        week.extend([None] * start_weekday)

    day = first_day
    while day <= last_day:
        if len(week) == 7:
            weeks.append(week)
            week = []
        week.append(day)
        day += timedelta(days=1)

    if week:
        weeks.append(week + [None] * (7 - len(week)))

    # Chỉ admin được phép xem danh sách nhân viên
    staff = NhanVien.objects.filter(
        trang_thai='dang_lam') if request.user.loai_tk == 'admin' else NhanVien.objects.none()

    # Nhân viên chỉ được xem lịch làm việc của chính mình
    if request.user.loai_tk == 'nhan_vien':
        try:
            staff_profile = NhanVien.objects.get(tai_khoan=request.user)
            schedules = LichLamViec.objects.filter(
                ngay_lam__range=[first_day, last_day],
                nhan_vien=staff_profile
            ).select_related('nhan_vien')
        except NhanVien.DoesNotExist:
            schedules = LichLamViec.objects.none()
    else:
        schedules = LichLamViec.objects.filter(
            ngay_lam__range=[first_day, last_day]
        ).select_related('nhan_vien')

    try:
        staff_profile = NhanVien.objects.get(tai_khoan=request.user) if request.user.loai_tk == 'nhan_vien' else None
    except NhanVien.DoesNotExist:
        staff_profile = None

    # Chỉ admin được phép thêm ca làm việc
    form = None
    if request.user.loai_tk == 'admin':
        form = LichLamViecForm(request.POST or None, initial={'ngay_lam': today})
        if request.method == 'POST' and form.is_valid():
            try:
                existing = LichLamViec.objects.filter(
                    nhan_vien=form.cleaned_data['nhan_vien'],
                    ngay_lam=form.cleaned_data['ngay_lam'],
                    ca_lam=form.cleaned_data['ca_lam']
                ).exists()

                if existing:
                    messages.error(request, "Nhân viên đã có lịch làm việc này")
                else:
                    form.save()
                    messages.success(request, "Đã thêm lịch làm việc")
                    return redirect('admin_schedule_management')
            except Exception as e:
                messages.error(request, f"Có lỗi xảy ra: {str(e)}")
        elif request.method == 'POST':
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    context = {
        'current_date': current_date,
        'prev_month': prev_month,
        'next_month': next_month,
        'weeks': weeks,
        'staff': staff,
        'schedules': schedules,
        'form': form,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
        'staff_profile': staff_profile,
    }
    return render(request, 'admin/schedule_management.html', context)
@login_required
@user_passes_test(lambda u: u.is_authenticated and getattr(u, 'loai_tk', '').strip().lower() in ['admin', 'nhan_vien'])
def delete_schedule(request, pk):
    logger.debug(f"User accessing delete_schedule: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    if not is_admin(request.user):
        messages.error(request, "Bạn không có quyền truy cập chức năng này.")
        return redirect('admin_schedule_management')

    schedule = get_object_or_404(LichLamViec, pk=pk)

    if request.method == 'POST':
        schedule.delete()
        messages.success(request, "Đã xóa lịch làm việc")
        return redirect('admin_schedule_management')

    context = {
        'schedule': schedule,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
    }
    return render(request, 'admin/delete_schedule.html', context)

@login_required
@user_passes_test(lambda u: u.is_authenticated and getattr(u, 'loai_tk', '').strip().lower() in ['admin', 'nhan_vien'])
def admin_request_management(request):
    logger.debug(f"User accessing admin_request_management: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    requests_list = YeuCau.objects.all().order_by('-ngay_tao')

    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')

    if search_query:
        requests_list = requests_list.filter(
            Q(ma_yc__icontains=search_query) |
            Q(khach_hang__ten_kh__icontains=search_query) |
            Q(phong__ten_p__icontains=search_query) |
            Q(noi_dung_yc__icontains=search_query)
        )

    if status_filter:
        requests_list = requests_list.filter(tinh_trang=status_filter)

    paginator = Paginator(requests_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
    }
    return render(request, 'admin/request_management.html', context)

@login_required
@user_passes_test(lambda u: u.is_authenticated and getattr(u, 'loai_tk', '').strip().lower() in ['admin', 'nhan_vien'])
def process_request(request, pk):
    logger.debug(f"User accessing process_request: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    yeu_cau = get_object_or_404(YeuCau, pk=pk)

    try:
        staff_profile = NhanVien.objects.get(tai_khoan=request.user) if request.user.loai_tk == 'nhan_vien' else None
    except NhanVien.DoesNotExist:
        staff_profile = None

    if request.user.loai_tk == 'nhan_vien' and yeu_cau.nhan_vien and staff_profile and yeu_cau.nhan_vien != staff_profile:
        messages.error(request, "Bạn không có quyền xử lý yêu cầu này.")
        return redirect('admin_dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        staff_id = request.POST.get('staff')
        note = request.POST.get('note', '')

        status_changed = False
        note_changed = (yeu_cau.ghi_chu != note)

        # Chỉ admin được phân công nhân viên
        if action == 'assign':
            if request.user.loai_tk != 'admin':
                messages.error(request, "Bạn không có quyền thực hiện hành động này.")
                return redirect('process_request', pk=pk)
            if staff_id:
                staff_member = get_object_or_404(NhanVien, pk=staff_id)
                if yeu_cau.nhan_vien != staff_member:
                    yeu_cau.nhan_vien = staff_member
                    status_changed = True
                if yeu_cau.tinh_trang != 'da_phan_cong':
                    yeu_cau.tinh_trang = 'da_phan_cong'
                    status_changed = True
            else:
                messages.error(request, "Vui lòng chọn nhân viên để phân công.")
                return redirect('process_request', pk=pk)

        elif action == 'processing':
            if yeu_cau.tinh_trang != 'dang_xu_ly':
                yeu_cau.tinh_trang = 'dang_xu_ly'
                if request.user.loai_tk == 'nhan_vien' and not yeu_cau.nhan_vien and staff_profile:
                    yeu_cau.nhan_vien = staff_profile
                status_changed = True

        elif action == 'complete':
            if yeu_cau.tinh_trang != 'da_xu_ly':
                yeu_cau.tinh_trang = 'da_xu_ly'
                yeu_cau.thoi_gian_hoan_thanh = timezone.now()
                status_changed = True

        elif action == 'cancel':
            if yeu_cau.tinh_trang != 'da_huy':
                yeu_cau.tinh_trang = 'da_huy'
                status_changed = True

        else:
            if note_changed:
                yeu_cau.ghi_chu = note
                yeu_cau.save()
                messages.success(request, "Đã cập nhật ghi chú cho yêu cầu.")
            else:
                messages.info(request, "Không có hành động nào được chọn hoặc không có thay đổi ghi chú.")
            return redirect('process_request', pk=pk)

        if status_changed or note_changed:
            yeu_cau.ghi_chu = note
            yeu_cau.save()
            messages.success(request, f"Yêu cầu đã được cập nhật: {action}.")
        else:
            messages.info(request, "Không có thay đổi nào được thực hiện.")

        return redirect('process_request', pk=pk)

    available_staff = NhanVien.objects.filter(trang_thai='dang_lam') if request.user.loai_tk == 'admin' else []

    context = {
        'yeu_cau': yeu_cau,
        'available_staff': available_staff,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
        'staff_profile': staff_profile,
    }
    return render(request, 'admin/process_request.html', context)

@login_required
@user_passes_test(lambda u: u.is_authenticated and getattr(u, 'loai_tk', '').strip().lower() in ['admin', 'nhan_vien'])
def admin_service_booking(request):
    logger.debug(f"User accessing admin_service_booking: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    service_bookings = DonDatDichVu.objects.all().order_by('-ngay_su_dung')

    all_services = DichVu.objects.all()

    search_query = request.GET.get('search', '')
    service_id = request.GET.get('service', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')

    if search_query:
        service_bookings = service_bookings.filter(
            Q(don_dat_phong__khach_hang__ten_kh__icontains=search_query) |
            Q(dich_vu__ten_dv__icontains=search_query) |
            Q(don_dat_phong__phong__ten_p__icontains=search_query))

    if service_id:
        service_bookings = service_bookings.filter(dich_vu__ma_dv=service_id)

    if start_date_str:
        try:
            start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            service_bookings = service_bookings.filter(ngay_su_dung__gte=start_date_obj)
        except ValueError:
            pass

    if end_date_str:
        try:
            end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            service_bookings = service_bookings.filter(ngay_su_dung__lte=end_date_obj)
        except ValueError:
            pass

    paginator = Paginator(service_bookings, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'all_services': all_services,
        'search_query': search_query,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'service_id': service_id,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
    }
    return render(request, 'admin/service_booking.html', context)

@login_required
@user_passes_test(lambda u: u.is_authenticated and getattr(u, 'loai_tk', '').strip().lower() in ['admin', 'nhan_vien'])
def admin_booking_history(request):
    logger.debug(f"User accessing admin_booking_history: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    bookings = DonDatPhong.objects.all().order_by('-ngay_dat')
    context = {
        'bookings': bookings,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
    }
    return render(request, 'admin/booking_history.html', context)

@login_required
@user_passes_test(lambda u: u.is_authenticated and getattr(u, 'loai_tk', '').strip().lower() in ['admin', 'nhan_vien'])
def admin_support_management(request):
    logger.debug(f"User accessing admin_support_management: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    support_requests = YeuCau.objects.all().order_by('-ngay_tao')
    context = {
        'requests': support_requests,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
    }
    return render(request, 'admin/support_management.html', context)

@login_required
@user_passes_test(lambda u: u.is_authenticated and (getattr(u, 'loai_tk', '').strip().lower() in ['admin', 'nhan_vien'] or is_customer(u)))
def booking_detail(request, pk):
    logger.debug(f"User accessing booking_detail: {request.user.username}, Role: {getattr(request.user, 'loai_tk', 'N/A')}, Authenticated: {request.user.is_authenticated}")
    booking = get_object_or_404(DonDatPhong, pk=pk)

    if not (request.user.loai_tk in ['admin', 'nhan_vien'] or (hasattr(request.user, 'khachhang') and booking.khach_hang == request.user.khachhang)):
        messages.error(request, "Bạn không có quyền truy cập chi tiết đặt phòng này.")
        return redirect('home')

    ordered_services = DonDatDichVu.objects.filter(don_dat_phong=booking)
    available_services = DichVu.objects.filter(hoat_dong=True)

    # Format gia_ddp
    formatted_gia_ddp = "{:,.0f}".format(booking.gia_ddp) if booking.gia_ddp is not None else "0"

    # Format phi_dv for each service in available_services
    for service in available_services:
        service.formatted_phi_dv = "{:,.0f}".format(service.phi_dv) if service.phi_dv is not None else "0"

    if request.method == 'POST' and (request.user.loai_tk in ['admin', 'nhan_vien'] or (hasattr(request.user, 'khachhang') and booking.khach_hang == request.user.khachhang)):
        if 'action' in request.POST:
            action = request.POST.get('action')

            if action == 'add_service':
                try:
                    service_id = request.POST.get('service_id')
                    service_date_str = request.POST.get('service_date')
                    service_time_str = request.POST.get('service_time')
                    quantity_str = request.POST.get('quantity')
                    note = request.POST.get('note', '')

                    if not all([service_id, service_date_str, service_time_str, quantity_str]):
                        messages.error(request, "Vui lòng điền đầy đủ thông tin dịch vụ.")
                        return redirect('booking_detail', pk=pk)

                    dich_vu = DichVu.objects.get(pk=service_id)
                    quantity = int(quantity_str)
                    service_date = datetime.strptime(service_date_str, '%Y-%m-%d').date()
                    service_time = datetime.strptime(service_time_str, '%H:%M').time()

                    if not (booking.ngay_nhan <= service_date <= booking.ngay_tra):
                        messages.error(request, "Ngày sử dụng dịch vụ phải nằm trong thời gian đặt phòng.")
                        return redirect('booking_detail', pk=pk)

                    don_dat_dich_vu = DonDatDichVu(
                        don_dat_phong=booking,
                        dich_vu=dich_vu,
                        ngay_su_dung=service_date,
                        gio_su_dung=service_time,
                        so_luong=quantity,
                        thanh_tien=dich_vu.phi_dv * quantity,
                        ghi_chu=note
                    )
                    don_dat_dich_vu.full_clean()
                    don_dat_dich_vu.save()

                    messages.success(request, "Đã thêm dịch vụ thành công.")
                    return redirect('booking_detail', pk=pk)

                except DichVu.DoesNotExist:
                    messages.error(request, "Dịch vụ không tồn tại.")
                except ValueError:
                    messages.error(request, "Dữ liệu không hợp lệ (số lượng, ngày, giờ).")
                except Exception as e:
                    logger.error(f"Error adding service: {str(e)}", exc_info=True)
                    messages.error(request, f"Có lỗi xảy ra khi thêm dịch vụ: {str(e)}")

            elif action == 'cancel' and booking.trang_thai == 'cho_xac_nhan':
                booking.trang_thai = 'da_huy'
                booking.save()
                messages.success(request, "Đã hủy đặt phòng.")
                return redirect('booking_detail', pk=pk)

    context = {
        'booking': booking,
        'services': ordered_services,
        'available_services': available_services,
        'is_admin': request.user.loai_tk == 'admin',
        'is_staff': request.user.loai_tk == 'nhan_vien',
        'is_customer': is_customer(request.user),
        'formatted_gia_ddp': formatted_gia_ddp,
    }
    return render(request, 'core/booking_detail.html', context)
# ------------------- Customer Views (Customer Only) -------------------

@login_required
@user_passes_test(is_customer)
def customer_bookings(request):
    if not hasattr(request.user, 'khachhang'):
        messages.error(request, "Tài khoản không có thông tin khách hàng")
        return redirect('home')

    search_query = request.GET.get('search', '')
    sort_by = request.GET.get('sort', '-ngay_dat')

    bookings_qs = DonDatPhong.objects.filter(khach_hang=request.user.khachhang)

    if search_query:
        bookings_qs = bookings_qs.filter(
            Q(ma_ddp__icontains=search_query) |
            Q(phong__ten_p__icontains=search_query) |
            Q(phong__loai_p__icontains=search_query)
        )

    if sort_by in ['ngay_dat', '-ngay_dat', 'ngay_nhan', '-ngay_nhan', 'trang_thai']:
        bookings_qs = bookings_qs.order_by(sort_by)
    else:
        bookings_qs = bookings_qs.order_by('-ngay_dat')

    paginator = Paginator(bookings_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'sort_by': sort_by,
        'current_sort': sort_by,
    }
    return render(request, 'core/customer_bookings.html', context)



@login_required
@user_passes_test(is_customer)
def customer_requests(request):
    if not hasattr(request.user, 'khachhang'):
        messages.error(request, "Bạn không có quyền truy cập mục này.")
        return redirect('home')

    confirmed_bookings = DonDatPhong.objects.filter(
        khach_hang=request.user.khachhang,
        trang_thai__in=['da_xac_nhan', 'da_checkin']
    ).order_by('-ngay_dat')

    context = {
        'bookings': confirmed_bookings,
    }
    return render(request, 'core/customer_requests.html', context)

@login_required
@user_passes_test(is_customer)
def request_detail(request, booking_pk):
    booking = get_object_or_404(DonDatPhong, pk=booking_pk)

    if not hasattr(request.user, 'khachhang') or booking.khach_hang != request.user.khachhang:
        messages.error(request, "Bạn không có quyền truy cập mục này.")
        return redirect('home')

    customer_requests_list = YeuCau.objects.filter(
        phong=booking.phong,
        khach_hang=request.user.khachhang
    ).order_by('-ngay_tao')

    if request.method == 'POST':
        form = YeuCauForm(request.POST)
        if form.is_valid():
            yeu_cau = form.save(commit=False)
            yeu_cau.khach_hang = request.user.khachhang
            yeu_cau.phong = booking.phong
            yeu_cau.save()
            messages.success(request, "Đã gửi yêu cầu thành công.")
            return redirect('request_detail', booking_pk=booking_pk)
        else:
            messages.error(request, "Vui lòng kiểm tra lại thông tin yêu cầu.")
    else:
        form = YeuCauForm(initial={'phong': booking.phong})

    context = {
        'booking': booking,
        'requests': customer_requests_list,
        'form': form,
    }
    return render(request, 'core/request_detail.html', context)

# ------------------- Profile Views (Customer and Staff) -------------------

@login_required
def profile(request):
    user = request.user
    new_url = request.session.pop('new_avatar_url', None)

    if hasattr(user, 'khachhang'):
        avatar_url = new_url if new_url else user.khachhang.anh_dai_dien.url
    else:
        avatar_url = new_url if new_url else user.nhanvien.anh_dai_dien.url

    return render(request, 'profile.html', {
        'user': user,
        'avatar_url': avatar_url,
        'is_admin': user.loai_tk == 'admin',
        'is_staff': user.loai_tk == 'nhan_vien',
        'is_customer': is_customer(user),
    })

@login_required
def profile_edit(request):
    user = request.user
    if hasattr(user, 'khachhang'):
        instance = user.khachhang
    else:
        instance = user.nhanvien

    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            profile = form.save()
            new_url = profile.anh_dai_dien.url
            request.session['new_avatar_url'] = new_url
            return redirect('profile')
    else:
        form = ProfileEditForm(instance=instance)

    return render(request, 'profile_edit.html', {
        'form': form,
        'is_admin': user.loai_tk == 'admin',
        'is_staff': user.loai_tk == 'nhan_vien',
        'is_customer': is_customer(user),
    })