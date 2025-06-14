from django.test import TestCase

# Create your tests here.
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from core.models import KhachHang
from django.core.files.uploadedfile import SimpleUploadedFile
from core.models import DonDatPhong, Phong, YeuCau
from django.utils import timezone
from datetime import timedelta

tai_khoan = get_user_model()

class ProfileViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.tai_khoan = tai_khoan.objects.create_tai_khoan(username='testuser', password='testpass', loai_tk='khach_hang')
        self.khachhang = KhachHang.objects.create(user=self.user, anh_dai_dien='default.jpg')

    def test_profile_view_logged_in(self):
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'profile.html')
        self.assertIn('user', response.context)
        self.assertIn('avatar_url', response.context)

    def test_profile_redirect_if_not_logged_in(self):
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 302)  # redirect to login page

class ProfileEditViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.tai_khoan = tai_khoan.objects.create_user(username='testuser2', password='testpass', loai_tk='khach_hang')
        self.khachhang = KhachHang.objects.create(user=self.user, anh_dai_dien='default.jpg')

    def test_profile_edit_get(self):
        self.client.login(username='testuser2', password='testpass')
        response = self.client.get(reverse('profile_edit'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'profile_edit.html')

    def test_profile_edit_post(self):
        self.client.login(username='testuser2', password='testpass')
        image = SimpleUploadedFile("newpic.jpg", b"file_content", content_type="image/jpeg")
        response = self.client.post(reverse('profile_edit'), {
            'ho_ten': 'New Name',
            'so_dien_thoai': '0123456789',
            'dia_chi': '123 Street',
            'anh_dai_dien': image,
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.khachhang.refresh_from_db()
        self.assertEqual(self.khachhang.ho_ten, 'New Name')


class CustomerBookingViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = tai_khoan.objects.create_user(username='cus1', password='123', loai_tk='khach_hang')
        self.khachhang = KhachHang.objects.create(user=self.user, anh_dai_dien='default.jpg')

        self.phong = Phong.objects.create(ten_p='P101', loai_p='VIP')
        self.ddp = DonDatPhong.objects.create(
            khach_hang=self.khachhang,
            phong=self.phong,
            ngay_dat=timezone.now(),
            ngay_nhan=timezone.now() + timedelta(days=1),
            trang_thai='cho_xac_nhan'
        )

    def test_customer_bookings_success(self):
        self.client.login(username='cus1', password='123')
        response = self.client.get(reverse('customer_bookings'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'templates/core/customer_bookings.html')
        self.assertIn('page_obj', response.context)

    def test_customer_bookings_not_customer(self):
        other_user = tai_khoan.objects.create_user(username='staff1', password='123', loai_tk='nhan_vien')
        self.client.login(username='staff1', password='123')
        response = self.client.get(reverse('customer_bookings'))
        self.assertEqual(response.status_code, 302)  # bị redirect vì không phải customer


class RequestDetailViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = tai_khoan.objects.create_user(username='cus2', password='123', loai_tk='khach_hang')
        self.khachhang = KhachHang.objects.create(user=self.user, anh_dai_dien='default.jpg')

        self.phong = Phong.objects.create(ten_p='P102', loai_p='Standard')
        self.ddp = DonDatPhong.objects.create(
            khach_hang=self.khachhang,
            phong=self.phong,
            ngay_dat=timezone.now(),
            ngay_nhan=timezone.now() + timedelta(days=2),
            trang_thai='da_xac_nhan'
        )

    def test_request_detail_get_success(self):
        self.client.login(username='cus2', password='123')
        response = self.client.get(reverse('request_detail', kwargs={'booking_pk': self.ddp.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'templates/core/request_detail.html')
        self.assertIn('form', response.context)

    def test_request_detail_post_success(self):
        self.client.login(username='cus2', password='123')
        response = self.client.post(
            reverse('request_detail', kwargs={'booking_pk': self.ddp.pk}),
            data={'noi_dung': 'Cần thêm khăn tắm'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(YeuCau.objects.filter(noi_dung='Cần thêm khăn tắm').exists())

    def test_request_detail_not_owner(self):
        other_user = tai_khoan.objects.create_user(username='other', password='123', loai_tk='khach_hang')
        other_kh = KhachHang.objects.create(user=other_user, anh_dai_dien='x.jpg')
        self.client.login(username='other', password='123')
        response = self.client.get(reverse('request_detail', kwargs={'booking_pk': self.ddp.pk}))
        self.assertEqual(response.status_code, 302)  # bị redirect vì không phải chủ đơn đặt phòng