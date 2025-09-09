from django.db import models
from django.utils import timezone

class Room(models.Model):
    ROOM_TYPE = (
        ('Single', 'Single'),
        ('Double', 'Double'),
        ('Triple', 'Triple'),
        ('Dorm', 'Dorm'),
    )
    STATUS_CHOICES = (
        ('Available', 'Available'),
        ('Occupied', 'Occupied'),
        ('Maintenance', 'Maintenance'),
    )

    room_id = models.AutoField(primary_key=True)
    room_number = models.CharField(max_length=20, unique=True)
    block_number = models.CharField(max_length=20)
    capacity = models.PositiveIntegerField(default=1)
    occupied = models.PositiveIntegerField(default=0)
    type = models.CharField(max_length=10, choices=ROOM_TYPE, default='Single')
    room_rent = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    image = models.ImageField(upload_to="room_images/", blank=True, null=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='Available')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)



