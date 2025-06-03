from django.db import models

# Create your models here.
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator

User = settings.AUTH_USER_MODEL

class Phong(models.Model):
    LOAI_PHONG_CHOICES = [
        ('standard', 'Phòng Standard'),
        ('deluxe', 'Phòng Deluxe'),
        ('suite', 'Phòng Suite'),
        ('family', 'Phòng Gia đình'),
    ]
    TRANG_THAI_CHOICES = [
        ('trong', 'Trống'),
        ('da_dat', 'Đã đặt'),
        ('dang_su_dung', 'Đang sử dụng'),
        ('bao_tri', 'Bảo trì'),
    ]
    ma_p = models.AutoField(primary_key=True)
    ten_p = models.CharField(max_length=50, unique=True)
    gia = models.FloatField(validators=[MinValueValidator(0)])
    loai_p = models.CharField(max_length=25, choices=LOAI_PHONG_CHOICES)
    chinh_sach_huy_p = models.TextField()
    mo_ta = models.TextField()
    anh_dai_dien = models.ImageField(upload_to='phong/')
    trang_thai = models.CharField(max_length=20, choices=TRANG_THAI_CHOICES, default='trong')
    suc_chua = models.PositiveIntegerField(default=2)
    tien_ich = models.TextField(blank=True)

    def __str__(self):
        return f"{self.ten_p} - {self.get_loai_p_display()}"

    @property
    def guest_range(self):
        return range(1, self.suc_chua + 1)

# Model mới cho ảnh của phòng
class AnhPhong(models.Model):
    phong = models.ForeignKey(Phong, related_name='anh_phu', on_delete=models.CASCADE) # QUAN TRỌNG: related_name='anh_phu'
    anh = models.ImageField(upload_to='phong_phu/')
    mo_ta_anh = models.CharField(max_length=200, blank=True, null=True, verbose_name="Mô tả ảnh")

    def __str__(self):
        return f"Ảnh cho {self.phong.ten_p} - {self.pk}"

class DichVu(models.Model):
    ma_dv = models.AutoField(primary_key=True)
    ten_dv = models.CharField(max_length=50)
    mo_ta = models.TextField()
    phi_dv = models.FloatField(validators=[MinValueValidator(0)])
    anh_dai_dien = models.ImageField(upload_to='dich_vu/')
    hoat_dong = models.BooleanField(default=True)

    def __str__(self):
        return self.ten_dv


class KhachHang(models.Model):
    ma_kh = models.AutoField(primary_key=True)
    tai_khoan = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ten_kh = models.CharField(max_length=50)
    sdt = models.CharField(max_length=10)
    email = models.EmailField()
    dia_chi = models.TextField()
    anh_dai_dien = models.ImageField(upload_to='khach_hang/', null=True, blank=True)
    ghi_chu = models.TextField(blank=True)

    def __str__(self):
        return self.ten_kh


class NhanVien(models.Model):
    GIOI_TINH_CHOICES = [
        ('Nam', 'Nam'),
        ('Nu', 'Nữ'),
        ('Khac', 'Khác'),
    ]
    TRANG_THAI_CHOICES = [
        ('dang_lam', 'Đang làm'),
        ('nghi_viec', 'Nghỉ việc'),
        ('nghi_phep', 'Nghỉ phép'),
    ]
    VI_TRI_CHOICES = [
        ('le_tan', 'Lễ tân'),
        ('buong_phong', 'Buồng phòng'),
        ('phuc_vu', 'Phục vụ'),
        ('quan_ly', 'Quản lý'),
        ('ky_thuat', 'Kỹ thuật'),
    ]
    ma_nv = models.AutoField(primary_key=True)
    tai_khoan = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    ten_nv = models.CharField(max_length=50)
    gioi_tinh = models.CharField(max_length=10, choices=GIOI_TINH_CHOICES)
    sdt = models.CharField(max_length=10)
    email = models.EmailField()
    dia_chi = models.TextField()
    vi_tri = models.CharField(max_length=30, choices=VI_TRI_CHOICES)
    trang_thai = models.CharField(max_length=20, choices=TRANG_THAI_CHOICES, default='dang_lam')
    ngay_vao_lam = models.DateField()
    anh_dai_dien = models.ImageField(upload_to='nhan_vien/', null=True, blank=True)

    def __str__(self):
        return self.ten_nv


class LichLamViec(models.Model):
    CA_LAM_CHOICES = [
        ('sang', 'Ca sáng (7h00-15h00)'),
        ('chieu', 'Ca chiều (15h00-13h00)'),
        ('toi', 'Ca tối (23h00-7h00)'),
    ]
    ma_lich = models.AutoField(primary_key=True)
    nhan_vien = models.ForeignKey(NhanVien, on_delete=models.CASCADE)
    ngay_lam = models.DateField()
    ca_lam = models.CharField(max_length=20, choices=CA_LAM_CHOICES)
    ghi_chu = models.TextField(blank=True)

    class Meta:
        unique_together = ('nhan_vien', 'ngay_lam', 'ca_lam')

    def __str__(self):
        return f"{self.nhan_vien.ten_nv} - {self.ngay_lam} - {self.get_ca_lam_display()}"


class DonDatPhong(models.Model):
    TRANG_THAI_CHOICES = [
        ('cho_xac_nhan', 'Chờ xác nhận'),
        ('da_xac_nhan', 'Đã xác nhận'),
        ('da_checkin', 'Đã check-in'),
        ('da_checkout', 'Đã check-out'),
        ('da_huy', 'Đã hủy'),
    ]
    ma_ddp = models.AutoField(primary_key=True)
    khach_hang = models.ForeignKey(KhachHang, on_delete=models.CASCADE)
    phong = models.ForeignKey(Phong, on_delete=models.CASCADE)
    ngay_dat = models.DateTimeField(auto_now_add=True)
    ngay_nhan = models.DateField()
    ngay_tra = models.DateField()
    so_luong_nguoi = models.PositiveIntegerField(default=1)
    gia_ddp = models.FloatField(validators=[MinValueValidator(0)])
    trang_thai = models.CharField(max_length=20, choices=TRANG_THAI_CHOICES, default='cho_xac_nhan')
    ghi_chu = models.TextField(blank=True)
    da_thanh_toan = models.BooleanField(default=False)

    def __str__(self):
        return f"Đặt phòng #{self.ma_ddp} - {self.khach_hang.ten_kh}"


class DonDatDichVu(models.Model):
    ma_ddv = models.AutoField(primary_key=True)
    don_dat_phong = models.ForeignKey(DonDatPhong, on_delete=models.CASCADE)
    dich_vu = models.ForeignKey(DichVu, on_delete=models.CASCADE)
    ngay_su_dung = models.DateField()
    gio_su_dung = models.TimeField()
    so_luong = models.PositiveIntegerField(default=1)
    thanh_tien = models.FloatField(validators=[MinValueValidator(0)])
    ghi_chu = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        self.thanh_tien = self.dich_vu.phi_dv * self.so_luong
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.don_dat_phong} - {self.dich_vu.ten_dv}"


class YeuCau(models.Model):
    LOAI_YC_CHOICES = [
        ('buong_phong', 'Buồng phòng'),
        ('ky_thuat', 'Kỹ thuật'),
        ('phuc_vu', 'Phục vụ'),
        ('le_tan', 'Lễ tân'),
        ('khac', 'Khác'),
    ]
    TINH_TRANG_CHOICES = [
        ('cho_phan_cong', 'Chưa phân công'),
        ('da_phan_cong', 'Đã phân công'),
        ('dang_xu_ly', 'Đang xử lý'),
        ('da_xu_ly', 'Đã xử lý'),
        ('da_huy', 'Đã hủy'),
    ]
    ma_yc = models.AutoField(primary_key=True)
    nhan_vien = models.ForeignKey(NhanVien, on_delete=models.SET_NULL, null=True, blank=True)
    khach_hang = models.ForeignKey(KhachHang, on_delete=models.CASCADE)
    phong = models.ForeignKey(Phong, on_delete=models.CASCADE)
    loai_yc = models.CharField(max_length=20, choices=LOAI_YC_CHOICES)
    noi_dung_yc = models.TextField()
    ngay_tao = models.DateTimeField(auto_now_add=True)
    ngay_cap_nhat = models.DateTimeField(auto_now=True)
    tinh_trang = models.CharField(max_length=30, choices=TINH_TRANG_CHOICES, default='cho_phan_cong')
    thoi_gian_hoan_thanh = models.DateTimeField(null=True, blank=True)
    ghi_chu = models.TextField(blank=True)

    def __str__(self):
        return f"YC {self.ma_yc} - {self.get_loai_yc_display()}"



class HoaDon(models.Model):
    ma_hd = models.AutoField(primary_key=True)
    don_dat_phong = models.OneToOneField(DonDatPhong, on_delete=models.CASCADE)
    ngay_tao = models.DateTimeField(auto_now_add=True)
    tong_tien = models.FloatField(validators=[MinValueValidator(0)])
    da_thanh_toan = models.BooleanField(default=False)
    phuong_thuc_tt = models.CharField(max_length=50, blank=True)
    ghi_chu = models.TextField(blank=True)

    def __str__(self):
        return f"Hóa đơn #{self.ma_hd} - {self.don_dat_phong}"