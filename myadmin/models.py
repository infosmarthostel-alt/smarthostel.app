from django.db import models
from django.utils import timezone
import enum





class login(models.Model):
    USERTYPE_CHOICES = (
        ('admin', 'Admin'),
        ('staff', 'Staff'),
        ('student', 'Student'),
        ('blocked', 'Blocked'), 
    )

    username = models.CharField(unique=True, max_length=255)
    password = models.CharField(max_length=100)
    usertype = models.CharField(max_length=10, choices=USERTYPE_CHOICES, default='student')
    is_active = models.BooleanField(default=True)
    failed_attempts = models.PositiveIntegerField(default=0)
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(blank=True, null=True)




class Weekday(enum.Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

class Meal(models.Model):
    MEAL_TYPE = (
        ('Breakfast', 'Breakfast'),
        ('Lunch', 'Lunch'),
        ('Dinner', 'Dinner'),
        ('Snack', 'Snack'),
    )

    meal_id = models.AutoField(primary_key=True)
    meal_pic = models.FileField(upload_to='meal_pic/', null=True, blank=True)
    meal_name = models.CharField(max_length=100)
    meal_type = models.CharField(max_length=10, choices=MEAL_TYPE)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    weekday = models.IntegerField(
        choices=[(day.value, day.name.title()) for day in Weekday]
    )
    created_at = models.DateTimeField(auto_now_add=True)



class Notification(models.Model):


    notification_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=150)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

class Complaint(models.Model):
    COMPLAINT_TYPE_CHOICES = (
        ('room', 'Room'),
        ('maintenance', 'Maintenance'),
        ('billing', 'Billing'),
        ('mess', 'Mess / Food'),
        ('other', 'Other'),
    )

    STATUS_CHOICES = (
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    )

    complaint_id = models.AutoField(primary_key=True)
    student = models.ForeignKey('student.Student', on_delete=models.CASCADE, related_name='complaints')
    room = models.ForeignKey('room.Room', null=True, blank=True, on_delete=models.SET_NULL, related_name='complaints')
    title = models.CharField(max_length=200)
    description = models.TextField()
    complaint_type = models.CharField(max_length=20, choices=COMPLAINT_TYPE_CHOICES, default='other')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    attachment = models.FileField(upload_to='complaint_attachments/', null=True, blank=True)
    admin_response = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.get_status_display()}] {self.title} - {self.student.name}'