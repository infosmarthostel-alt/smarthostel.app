from collections import defaultdict
from django import forms
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.db import transaction
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.utils.dateparse import parse_date

from myadmin.models import Complaint, Meal, Notification, Weekday
from .models import Student, Room, login as LoginModel

def s_home(request):
    if request.session.get('sid') == 'out':
        return HttpResponse("<script>alert('please login');window.location='/'</script>")

    student = _get_student_from_session(request)
    notifications = Notification.objects.filter(is_active=True).order_by('-created_at')

    room = student.room if student and student.room else None
    today = timezone.localdate()
    weekday_num = today.weekday()  # 0 = Monday ... 6 = Sunday

    # get all meals matching today's weekday
    meals_qs = Meal.objects.filter(weekday=weekday_num).order_by('meal_type', 'meal_name')

    # group by meal_type (dict: meal_type -> [Meal, ...])
    grouped = defaultdict(list)
    for m in meals_qs:
        grouped[m.meal_type].append(m)

    # readable weekday name (using Weekday enum)
    try:
        weekday_name = Weekday(weekday_num).name.title()
    except Exception:
        weekday_name = today.strftime('%A')  # fallback

    # --- ROOMMATES: other students in same room (exclude current student) ---
    if room:
        # use related_name 'students' from Room model
        roommates_qs = room.students.exclude(student_id=student.student_id).order_by('name')
        # optionally prefetch/select related fields if you will display related objects
        # roommates_qs = roommates_qs.select_related('login')  # example, if needed
    else:
        roommates_qs = Student.objects.none()

    return render(request, "home.html", {
        'student': student,
        'room': room,
        'notifications': notifications,
        'weekday_num': weekday_num,
        'weekday_name': weekday_name,
        'meals_by_type': dict(grouped),
        'roommates': roommates_qs,
    })

from django.db.models import Count

# add this helper view
def room_programme_counts(request):
    programme = request.GET.get('programme')  # may be None or empty
    # Get counts in a single DB query (efficient)
    if programme:
        qs = (
            Student.objects
            .filter(programme=programme, room__isnull=False)
            .values('room')
            .annotate(count=Count('pk'))
        )
        data = {str(item['room']): item['count'] for item in qs}
    else:
        data = {}

    # ensure every room key exists (0 if none)
    room_ids = Room.objects.values_list('pk', flat=True)
    for rid in room_ids:
        data.setdefault(str(rid), 0)

    return JsonResponse({'counts': data})


def student_register(request):
    rooms = Room.objects.all().order_by('room_number')
    rooms_with_avail = []
    for r in rooms:
        avail = max(r.capacity - r.occupied, 0)
        rooms_with_avail.append({
            'instance': r,
            'available': avail,
        })

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        age = request.POST.get('age') or None
        gender = request.POST.get('gender') or None
        phone = request.POST.get('phone') or ''
        email = request.POST.get('email') or ''
        password = request.POST.get('password') or ''
        parent_name = request.POST.get('parent_name') or ''
        parent_phone = request.POST.get('parent_phone') or ''
        parent_email = request.POST.get('parent_email') or ''
        district = request.POST.get('district') or None
        programme = request.POST.get('programme') or None
        pincode = request.POST.get('pincode') or ''
        joined_date = request.POST.get('joined_date') or None
        preferred_room_id = request.POST.get('preferred_room')
        profile_pic_file = request.FILES.get('profile')
        id_proof_file = request.FILES.get('id_proof')

        # Basic validation
        if not name:
            messages.error(request, 'Name is required.')
            return render(request, 'student_register.html', {
                'rooms': rooms_with_avail,
                'post': request.POST,
            })

        try:
            age_val = int(age) if age is not None and age != '' else None
        except ValueError:
            messages.error(request, 'Age must be a number.')
            return render(request, 'student_register.html', {
                'rooms': rooms_with_avail,
                'post': request.POST,
            })

        # If email provided, don't allow duplicate usernames
        login_obj = None
        if email:
            if LoginModel.objects.filter(username=email).exists():
                messages.error(request, 'An account with this email already exists. Please login or use another email.')
                return render(request, 'student_register.html', {
                    'rooms': rooms_with_avail,
                    'post': request.POST,
                })
            if not password:
                messages.error(request, 'Password is required when providing an email for login.')
                return render(request, 'student_register.html', {
                    'rooms': rooms_with_avail,
                    'post': request.POST,
                })

            # create login object and store hashed password
            hashed = make_password(password)
            login_obj = LoginModel.objects.create(
                username=email,
                password=hashed,
                usertype='student',
                is_active=True,
                date_joined=timezone.now()
            )

        # Create student (with or without room reservation)
        if preferred_room_id:
            try:
                with transaction.atomic():
                    room = Room.objects.select_for_update().get(pk=int(preferred_room_id))

                    if room.occupied >= room.capacity:
                        messages.error(request, f"Selected room '{room.room_number}' is full. Choose another room.")
                        raise ValueError("Room full")

                    student = Student(
                        name=name,
                        age=age_val,
                        gender=gender,
                        phone=phone,
                        email=email or None,
                        parent_name=parent_name or None,
                        parent_phone=parent_phone or None,
                        parent_email=parent_email or None,
                        district=district or None,
                        programme=programme or None,
                        pincode=pincode or None,
                        joined_date=joined_date or None,
                        id_proof=id_proof_file if id_proof_file else None,
                        profile_pic=profile_pic_file if profile_pic_file else None,
                        login=login_obj if login_obj else None,
                    )
                    student.room = room
                    student.save()
                    room.occupied = room.occupied + 1
                    if room.occupied >= room.capacity:
                        room.status = 'Occupied'
                    room.save()

                messages.success(request, 'Registration successful and room reserved.')
                return redirect('/')
            except Room.DoesNotExist:
                messages.error(request, 'Selected room not found.')
            except ValueError:
                pass
        else:
            student = Student(
                name=name,
                age=age_val,
                gender=gender,
                phone=phone,
                email=email or None,
                parent_name=parent_name or None,
                parent_phone=parent_phone or None,
                parent_email=parent_email or None,
                district=district or None,
                programme=programme or None,
                pincode=pincode or None,
                joined_date=joined_date or None,
                profile_pic=profile_pic_file if profile_pic_file else None,
                id_proof=id_proof_file if id_proof_file else None,
                login=login_obj if login_obj else None,
            )
            student.save()
            messages.success(request, 'Registration successful (no room reserved).')
            return redirect('/')

    return render(request, 'student_register.html', {
        'rooms': rooms_with_avail,
    })



def _get_student_from_session(request):
    lid = request.session.get('sid')
    if not lid:
        return None
    return Student.objects.filter(login_id=lid).first()

@csrf_protect
def view_profile(request):
    student = _get_student_from_session(request)
    if not student:
        messages.error(request, "Could not find your profile. Please login.")
        return redirect('login')
    return render(request, 'profile_view.html', {'student': student})

@csrf_protect
def edit_profile(request):
    student = _get_student_from_session(request)
    if not student:
        messages.error(request, "Please login to edit your profile.")
        return redirect('login')

    errors = {}
    if request.method == 'POST':
        # get POST values (only editable fields)
        name = request.POST.get('name', '').strip()
        age = request.POST.get('age', '').strip()
        gender = request.POST.get('gender', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()

        parent_name = request.POST.get('parent_name', '').strip()
        parent_phone = request.POST.get('parent_phone', '').strip()
        parent_email = request.POST.get('parent_email', '').strip()

        district = request.POST.get('district', '').strip()
        pincode = request.POST.get('pincode', '').strip()
        joined_date = request.POST.get('joined_date', '').strip()

        # Basic validation (add more if you want)
        if not name:
            errors['name'] = "Name is required."
        if age:
            try:
                age_val = int(age)
                if age_val < 0:
                    errors['age'] = "Age cannot be negative."
            except ValueError:
                errors['age'] = "Age must be an integer."
        else:
            age_val = None

        # If email provided, do a very simple check
        if email and '@' not in email:
            errors['email'] = "Enter a valid email."

        # handle profile picture upload
        if 'profile_pic' in request.FILES:
            profile_file = request.FILES['profile_pic']
            student.profile_pic = profile_file

        # If no errors, save fields
        if not errors:
            student.name = name or student.name
            student.age = age_val
            student.gender = gender or student.gender
            student.phone = phone or student.phone
            student.email = email or student.email

            student.parent_name = parent_name or student.parent_name
            student.parent_phone = parent_phone or student.parent_phone
            student.parent_email = parent_email or student.parent_email

            student.district = district or student.district
            student.pincode = pincode or student.pincode

            # joined_date: parse YYYY-MM-DD or empty
            if joined_date:
                d = parse_date(joined_date)
                if d:
                    student.joined_date = d

            student.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('profile_view')
        else:
            messages.error(request, "Please correct the errors below.")

    # send choices to template to render selects
    context = {
        'student': student,
        'errors': errors,
        'gender_choices': Student.GENDER_CHOICES,
        'district_choices': Student.DISTRICT_CHOICES,
    }
    return render(request, 'profile_edit.html', context)

@csrf_protect
@require_http_methods(["GET", "POST"])
def change_password(request):
    student = _get_student_from_session(request)
    if not student:
        messages.error(request, "Please login to change your password.")
        return redirect('login')

    login_obj = student.login
    errors = {}
    if request.method == 'POST':
        old = request.POST.get('old_password', '')
        new1 = request.POST.get('new_password1', '')
        new2 = request.POST.get('new_password2', '')

        if not old:
            errors['old_password'] = "Enter your old password."
        if not new1 or not new2:
            errors['new_password'] = "Enter new password and confirm it."
        elif new1 != new2:
            errors['new_password'] = "New passwords do not match."

        # verify old password (supports hashed or plain)
        ok = False
        try:
            ok = check_password(old, login_obj.password)
        except Exception:
            ok = False
        if not ok and old == login_obj.password:
            ok = True

        if not ok:
            errors['old_password'] = "Old password is incorrect."

        if not errors:
            login_obj.password = make_password(new1)
            login_obj.save()
            messages.success(request, "Password changed successfully.")
            return redirect('profile_view')
        else:
            messages.error(request, "Please correct the errors below.")

    return render(request, 'change_password.html', {'student': student, 'errors': errors})


def meals_today(request):
    """
    Render meals for today's weekday.
    Groups results by meal_type for easy display.
    """
    # Use timezone-aware local date so it respects TIME_ZONE and USE_TZ
    today = timezone.localdate()
    weekday_num = today.weekday()  # 0 = Monday ... 6 = Sunday

    # get all meals matching today's weekday
    meals_qs = Meal.objects.filter(weekday=weekday_num).order_by('meal_type', 'meal_name')

    # group by meal_type (dict: meal_type -> [Meal, ...])
    grouped = defaultdict(list)
    for m in meals_qs:
        grouped[m.meal_type].append(m)

    # readable weekday name (using Weekday enum)
    try:
        weekday_name = Weekday(weekday_num).name.title()
    except Exception:
        weekday_name = today.strftime('%A')  # fallback

    context = {
        'weekday_num': weekday_num,
        'weekday_name': weekday_name,
        'meals_by_type': dict(grouped),
    }
    return render(request, 'meals_today.html', context)


def notifications_list(request):
    """
    Render a list of notifications.
    By default show active notifications first, newest first.
    """
    notifications = Notification.objects.filter(is_active=True).order_by('-created_at')
    context = {
        'notifications': notifications,
    }
    return render(request, 'notifications.html', context) 


@require_http_methods(["GET", "POST"])
def student_submit_complaint(request):
    student = _get_student_from_session(request)
    if not student:
        messages.error(request, "Please log in to submit a complaint.")
        return redirect(reverse('login'))

    if request.method == 'POST':
        room = request.POST.get('room') or None
        title = request.POST.get('title')
        description = request.POST.get('description')
        complaint_type = request.POST.get('complaint_type')
        attachment = request.FILES.get('attachment')

        if not title or not description:
            messages.error(request, "Title and description are required.")
        else:
            comp = Complaint(
                student=student,
                title=title,
                description=description,
                complaint_type=complaint_type,
                attachment=attachment
            )
            # If student has a room assigned, always use it. Otherwise, allow free input
            if student.room:
                comp.room = student.room
            elif room:
                comp.room_id = room

            comp.save()
            messages.success(request, "Complaint submitted successfully.")
            return redirect(reverse('student_complaints_list'))

    return render(request, 'complaint_form.html', {'student': student})


@require_http_methods(["GET"])
def student_complaints_list(request):
    student = _get_student_from_session(request)
    if not student:
        messages.error(request, "Please log in to view your complaints.")
        return redirect(reverse('login'))

    complaints = student.complaints.all()
    return render(request, 'complaints_list.html', {'complaints': complaints})