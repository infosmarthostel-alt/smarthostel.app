from uuid import uuid4
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

from room.models import Room
from myadmin.models import login
from decimal import Decimal
from datetime import timedelta
from django.db.models import Sum
from django.db import transaction
from django.utils import timezone



class Student(models.Model):
    GENDER_CHOICES = (
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    )

    DISTRICT_CHOICES = (
        ('Kasaragod', 'Kasaragod'),
        ('Kannur', 'Kannur'),
        ('Wayanad', 'Wayanad'),
        ('Kozhikode', 'Kozhikode'),
        ('Malappuram', 'Malappuram'),
        ('Palakkad', 'Palakkad'),
        ('Thrissur', 'Thrissur'),
        ('Ernakulam', 'Ernakulam'),
        ('Idukki', 'Idukki'),
        ('Kottayam', 'Kottayam'),
        ('Alappuzha', 'Alappuzha'),
        ('Pathanamthitta', 'Pathanamthitta'),
        ('Kollam', 'Kollam'),
        ('Thiruvananthapuram', 'Thiruvananthapuram'),
    )
    
    PROGRAMME_CHOICES = (
        ('BCA', 'BCA - Bachelor of Computer Applications'),
        ('BSC_CS', 'B.Sc Computer Science'),
        ('BSC_IT', 'B.Sc Information Technology'),
        ('BTECH_CS', 'B.Tech Computer Science & Engineering'),
        ('BTECH_IT', 'B.Tech Information Technology'),
        ('BTECH_EC', 'B.Tech Electronics & Communication'),
        ('BTECH_EE', 'B.Tech Electrical Engineering'),
        ('BTECH_ME', 'B.Tech Mechanical Engineering'),
        ('BTECH_CE', 'B.Tech Civil Engineering'),
        ('BTECH_AE', 'B.Tech Aeronautical Engineering'),
        ('MCA', 'MCA - Master of Computer Applications'),
        ('MSC_CS', 'M.Sc Computer Science'),
        ('MTECH_CS', 'M.Tech Computer Science & Engineering'),
        ('MTECH_IT', 'M.Tech Information Technology'),
        ('MTECH_EC', 'M.Tech Electronics & Communication'),
        ('MTECH_ME', 'M.Tech Mechanical Engineering'),
        ('MTECH_CE', 'M.Tech Civil Engineering'),
        ('MBA', 'MBA - Master of Business Administration'),
        ('DIP_CS', 'Diploma in Computer Science'),
        ('DIP_CE', 'Diploma in Civil Engineering'),
        ('DIP_ME', 'Diploma in Mechanical Engineering'),
        ('DIP_EE', 'Diploma in Electrical Engineering'),
    )


    student_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=6, choices=GENDER_CHOICES, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(max_length=150, null=True, blank=True)

    parent_name = models.CharField(max_length=100, null=True, blank=True)
    parent_phone = models.CharField(max_length=20, null=True, blank=True)
    parent_email = models.EmailField(max_length=150, null=True, blank=True)

    district = models.CharField(max_length=50, choices=DISTRICT_CHOICES, null=True, blank=True)
    programme = models.CharField(max_length=50, choices=PROGRAMME_CHOICES, null=True, blank=True)
    pincode = models.CharField(max_length=10, null=True, blank=True)
    profile_pic = models.FileField(upload_to='profile_pic/', null=True, blank=True)
    id_proof = models.FileField(upload_to='id_proofs/', null=True, blank=True)

    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL, related_name='students')
    joined_date = models.DateField(null=True, blank=True)
    login = models.ForeignKey(login, on_delete=models.CASCADE, default=1)

    def __str__(self):
        return self.name
    
    def _room_rent_or_default(self):
        try:
            return Decimal(self.room.room_rent)
        except Exception:
            return Decimal('2000.00')

    def latest_successful_transaction(self):
        return self.transactions.filter(status='success', end_date__isnull=False).order_by('-end_date').first()

    def paid_until(self):
        tx = self.latest_successful_transaction()
        return tx.end_date if tx else None

    def is_rent_current(self):
        pu = self.paid_until()
        return bool(pu and pu >= timezone.now().date())

    def days_left_paid(self):
        pu = self.paid_until()
        if not pu:
            return 0
        return max((pu - timezone.now().date()).days, 0)

    def total_fees_paid(self):
        agg = self.fees.filter(status='Paid').aggregate(total=Sum('amount'))
        return agg['total'] or Decimal('0.00')

    def create_initiated_transaction(self, method='upi', amount=None, start_from=None, meta=None, fee=None):
        """
        Create a PaymentTransaction in 'initiated' state. The client completes via finalize endpoint after payment flow.
        - start_from: a date object from which the 30-day period should start (if None, computed at finalize time)
        - fee: optional Fee object; if provided, this is a payment for an existing unpaid fee (no period computation)
        """
        meta = meta or {}
        if fee:
            amount = fee.amount
            start_from = None  # No period for fee payments
            meta['fee_id'] = fee.fee_id

        if amount is None:
            amount = self._room_rent_or_default()
        if isinstance(amount, (int, float, str)):
            amount = Decimal(str(amount))

        # Compute start_from only if not for a specific fee
        today = timezone.now().date()
        if start_from is None and 'fee_id' not in meta:
            latest = self.latest_successful_transaction()
            if latest and latest.end_date and latest.end_date > today:
                start_from = latest.end_date
            else:
                start_from = today

        tx = PaymentTransaction.objects.create(
            student=self,
            amount=amount,
            method=method,
            status='initiated',
            start_date=start_from,
            meta=meta
        )
        return tx


class PaymentTransaction(models.Model):
    STATUS_CHOICES = (
        ('initiated', 'Initiated'),
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    )

    METHOD_CHOICES = (
        ('upi', 'UPI'),
        ('qr', 'QR'),
        ('card', 'Card'),
        ('netbanking', 'Netbanking'),
        ('wallet', 'Wallet'),
    )

    # Use a proper UUIDField with a callable default (importable)
    tx_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    student = models.ForeignKey('Student', on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='initiated')
    start_date = models.DateField(null=True, blank=True)   # when this paid period starts
    end_date = models.DateField(null=True, blank=True)     # when this paid period ends (start_date + 30)
    provider_txn_id = models.CharField(max_length=255, null=True, blank=True)  # external gateway id
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    meta = models.JSONField(null=True, blank=True)  # optional metadata (device, card-brand, etc)

    def mark_success(self, provider_txn_id=None):
        """Mark transaction successful and fill end_date = start_date + 30 days (or today if missing), but only if not for a specific fee."""
        if provider_txn_id:
            self.provider_txn_id = provider_txn_id
        today = timezone.now().date()
        if 'fee_id' not in self.meta:
            start = self.start_date if self.start_date else today
            self.start_date = start
            self.end_date = start + timedelta(days=30)
        self.status = 'success'
        self.save()


class Fee(models.Model):
    STATUS_CHOICES = (
        ('Paid', 'paid'),
        ('Unpaid', 'unpaid'),
        ('Pending', 'pending'),
    )

    fee_id = models.AutoField(primary_key=True)
    student = models.ForeignKey('Student', on_delete=models.CASCADE, related_name='fees')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='Unpaid')
    payment_date = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    payment_tx = models.ForeignKey(PaymentTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='fees')