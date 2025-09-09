from django.shortcuts import render
from decimal import Decimal, InvalidOperation
from pyexpat.errors import messages
from django.http import HttpResponse
from django import forms
from .models import Complaint, Meal, Notification, Weekday, login
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from datetime import datetime
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone
from django.db.models import F
from django.contrib import messages
from django.db import IntegrityError
from django.views.decorators.http import require_http_methods
from django.http import HttpResponseForbidden
import random
from datetime import timedelta
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.http import JsonResponse

def health_check(request):
    return JsonResponse({"status": "ok"})

def index(request):
    return render(request, "index.html")

def login_return(request):
    return render(request,"login.html")

def logout(request):
    request.session['lid'] = 'out'
    request.session['sid'] = 'out'
    return HttpResponse("<script>alert('logout');window.location='/'</script>")

def login_post(request):
    username = request.POST.get('textfield', '').strip()
    password = request.POST.get('textfield2', '')

  
    try:
        res = login.objects.get(username=username)
    except login.DoesNotExist:
        return HttpResponse("<script>alert('wrong password or username');window.location='/login_return'</script>")

    ok = False
    try:
        ok = check_password(password, res.password)
    except Exception:
        ok = False

    if not ok and password == res.password:
     
        ok = True

    if not ok:
        return HttpResponse("<script>alert('wrong password or username');window.location='/login_return'</script>")

    res.last_login = timezone.now()
    res.save(update_fields=['last_login'])

    # request.session['lid'] = res.id
    if res.usertype == "admin":
        request.session['lid'] = res.id
        return redirect('/admin/dashboard/')
    elif res.usertype == "student":
        request.session['sid'] = res.id
        return redirect('/s_home')
    elif res.usertype == "blocked":
        return HttpResponse("<script>alert('you are blocked');window.location='/'</script>")
    else:
        return HttpResponse("<script>alert('wrong usertype');window.location='/'</script>")


# views_admin.py
from decimal import Decimal
from datetime import date, datetime
import calendar

from student.models import Student,Fee,PaymentTransaction
from room.models import Room
from .models import  login as LoginModel


from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.db.models import Sum, Count, Q
from django.utils import timezone
from decimal import Decimal
import csv
from datetime import date, timedelta


# Decorator: simple admin check (adjust to your auth)
def admin_required(view_fn):
    def wrapped(request, *args, **kwargs):
        # Example: you probably have a custom session login mechanism.
        user_id = request.session.get('lid')  # change to your session key
        if not user_id:
            return redirect('your_login_url')  # change to your login route
        try:
            user = LoginModel.objects.get(pk=user_id)
        except LoginModel.DoesNotExist:
            return redirect('your_login_url')
        if user.usertype != 'admin':
            return HttpResponse('Forbidden', status=403)
        request.current_user = user
        return view_fn(request, *args, **kwargs)
    wrapped.__name__ = view_fn.__name__
    return wrapped


@admin_required
def admin_dashboard(request):
    today = timezone.now().date()
    first_day = today.replace(day=1)
    # revenue this month (based on payment end_date falling within month)
    revenue_month = PaymentTransaction.objects.filter(
        status='success',
        end_date__gte=first_day,
        end_date__lte=today
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    total_revenue = PaymentTransaction.objects.filter(status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    total_students = Student.objects.count()
    blocked_students = LoginModel.objects.filter(usertype='blocked').count()
    occupied_rooms = Room.objects.filter(occupied__gt=0).count()
    available_rooms = Room.objects.filter(status='Available').count()

    # upcoming unpaid fees this month (count)
    unpaid_count = Fee.objects.filter(
        status='Unpaid',
        due_date__gte=first_day,
        due_date__lte=(first_day + timedelta(days=31))
    ).count()

    context = {
        'revenue_month': revenue_month,
        'total_revenue': total_revenue,
        'total_students': total_students,
        'blocked_students': blocked_students,
        'occupied_rooms': occupied_rooms,
        'available_rooms': available_rooms,
        'unpaid_count': unpaid_count,
    }
    return render(request, 'dashboard.html', context)


@admin_required
def students_list(request):
    # filters: programme, district, payment_status (paid/unpaid/pending)
    qs = Student.objects.select_related('room', 'login').all().order_by('name')

    programme = request.GET.get('programme')
    district = request.GET.get('district')
    payment_status = request.GET.get('payment_status')
    search = request.GET.get('q')

    if programme:
        qs = qs.filter(programme=programme)
    if district:
        qs = qs.filter(district=district)
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search))

    if payment_status:
        if payment_status == 'paid':
            qs = [s for s in qs if s.is_rent_current()]
        elif payment_status == 'unpaid':
            qs = [s for s in qs if not s.is_rent_current()]

    # If payment_status filter used, qs is a list; we'll handle in template. For large data, better to precompute field.
    programmes = Student.PROGRAMME_CHOICES
    districts = Student.DISTRICT_CHOICES

    context = {
        'students': qs,
        'programmes': programmes,
        'districts': districts,
        'selected_programme': programme,
        'selected_district': district,
        'payment_status': payment_status,
        'search': search,
    }
    return render(request, 'students_list.html', context)

from django.db.models.functions import Coalesce

@admin_required
def student_detail(request, student_id):
    student = get_object_or_404(Student, student_id=student_id)

    # recent transactions and fees for display (non-sliced queries used below for totals)
    transactions = student.transactions.order_by('-created_at')[:20]
    all_fees_qs = student.fees.order_by('-due_date')   # full queryset (not sliced) used for calculations
    fees_display = all_fees_qs[:20]                   # keep a sliced list for the page if you prefer

    # --- PENDING / OVERDUE calculations ---
    pending_qs = all_fees_qs.filter(status__in=['Unpaid', 'Pending'])
    pending_count = pending_qs.count()
    pending_total = pending_qs.aggregate(
        total=Coalesce(Sum('amount'), Decimal('0.00'))
    )['total'] or Decimal('0.00')

    today = timezone.now().date()
    overdue_qs = pending_qs.filter(due_date__lt=today)
    overdue_count = overdue_qs.count()
    overdue_total = overdue_qs.aggregate(
        total=Coalesce(Sum('amount'), Decimal('0.00'))
    )['total'] or Decimal('0.00')

    # POST actions: assign_room, create_fee, mark_fee_paid
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'assign_room':
            room_id = request.POST.get('room_id')
            try:
                room = Room.objects.get(pk=room_id)
                if room.occupied < room.capacity:
                    # decrement previous room occupancy if switching rooms
                    if student.room and student.room.pk != room.pk:
                        prev = student.room
                        prev.occupied = max(prev.occupied - 1, 0)
                        prev.save()
                    student.room = room
                    student.save()
                    room.occupied = min(room.capacity, room.occupied + 1)
                    room.status = 'Occupied' if room.occupied > 0 else room.status
                    room.save()
                    messages.success(request, f'Room {room_id} assigned to {student.name}.')
                else:
                    messages.error(request, 'Selected room is full.')
            except Room.DoesNotExist:
                messages.error(request, 'Room not found.')
            return redirect(reverse('student_detail', args=[student_id]))

        elif action == 'create_fee':
            amount = request.POST.get('amount')
            due_date_str = request.POST.get('due_date')
            note = request.POST.get('note', '')
            try:
                # careful Decimal conversion
                amount_dec = Decimal(str(amount))
                due_date = date.fromisoformat(due_date_str)
                Fee.objects.create(student=student, amount=amount_dec, due_date=due_date, status='Unpaid', note=note)
                messages.success(request, 'Fee created.')
            except Exception as exc:
                messages.error(request, f'Could not create fee: {exc}')
            return redirect(reverse('student_detail', args=[student_id]))

        elif action == 'mark_fee_paid':
            fee_id = request.POST.get('fee_id')
            payment_tx_id = request.POST.get('payment_tx_id')  # optional: associate a PaymentTransaction
            try:
                fee = Fee.objects.get(pk=fee_id, student=student)
                fee.status = 'Paid'
                fee.payment_date = timezone.now().date()
                if payment_tx_id:
                    try:
                        tx = PaymentTransaction.objects.get(tx_id=payment_tx_id, student=student)
                        fee.payment_tx = tx
                        fee.transaction_id = tx.provider_txn_id or str(tx.tx_id)
                    except PaymentTransaction.DoesNotExist:
                        # ignore: optional linking only
                        pass
                fee.save()
                messages.success(request, 'Fee marked as paid.')
            except Fee.DoesNotExist:
                messages.error(request, 'Fee not found.')
            return redirect(reverse('student_detail', args=[student_id]))

    # rooms with vacancy (use F-expression to compare fields at DB level)
    available_rooms = Room.objects.filter(occupied__lt=F('capacity'))

    context = {
        'student': student,
        'transactions': transactions,
        'fees': fees_display,
        'all_fees_qs': all_fees_qs,   # if template needs full list
        'available_rooms': available_rooms,

        # pending/overdue summary
        'pending_count': pending_count,
        'pending_total': pending_total,
        'overdue_count': overdue_count,
        'overdue_total': overdue_total,
    }
    return render(request, 'student_detail.html', context)

@admin_required
def toggle_block_student(request, student_id):
    # Toggle block/unblock by changing the linked login.usertype to 'blocked' or 'student'
    student = get_object_or_404(Student, student_id=student_id)
    login_obj = student.login
    if not login_obj:
        return HttpResponseBadRequest('No login attached')

    # toggle
    if login_obj.usertype == 'blocked':
        login_obj.usertype = 'student'
        login_obj.is_active = True
        login_obj.save()
        status = 'unblocked'
    else:
        login_obj.usertype = 'blocked'
        login_obj.is_active = False
        login_obj.save()
        status = 'blocked'

    # If request is AJAX return json
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': status})
    return redirect(reverse('students_list'))


@admin_required
def rooms_list(request):
    rooms = Room.objects.all().order_by('block_number', 'room_number')
    # annotate occupancy %
    rooms_info = []
    for r in rooms:
        capacity = r.capacity or 1
        occ = r.occupied or 0
        pct = int((occ / capacity) * 100)
        students = r.students.all()  # related_name='students' on Student model
        rooms_info.append({'room': r, 'occupancy_pct': pct, 'students': students})
    context = {'rooms_info': rooms_info}
    return render(request, 'rooms_list.html', context)


@admin_required
def room_detail(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    students = room.students.all()

    if request.method == 'POST':
        room_rent = request.POST.get('room_rent')
        status = request.POST.get('status')
        try:
            if room_rent:
                room.room_rent = Decimal(room_rent)
            if status:
                room.status = status
            room.save()
        except Exception:
            pass
        return redirect(reverse('room_detail', args=[room_id]))

    context = {
        'room': room,
        'students': students,
        'status_choices': Room.STATUS_CHOICES 
    }
    return render(request, 'room_detail.html', context)




@admin_required
def create_room(request):
    type_choices = Room.ROOM_TYPE
    status_choices = Room.STATUS_CHOICES
    errors = []

    if request.method == 'POST':
        room_number = (request.POST.get('room_number') or '').strip()
        block_number = (request.POST.get('block_number') or '').strip()
        capacity_raw = request.POST.get('capacity') or '1'
        room_rent_raw = request.POST.get('room_rent') or '0.00'
        room_type = request.POST.get('type') or type_choices[0][0]
        status = request.POST.get('status') or status_choices[0][0]
        image = request.FILES.get('image')  # file upload

        # basic validation
        if not room_number:
            errors.append('Room number is required.')
        if not block_number:
            errors.append('Block number is required.')

        try:
            capacity = int(capacity_raw)
            if capacity < 1:
                raise ValueError
        except ValueError:
            errors.append('Capacity must be an integer >= 1.')
            capacity = 1

        try:
            room_rent = Decimal(room_rent_raw)
        except (InvalidOperation, TypeError):
            errors.append('Invalid room rent; using 0.00.')
            room_rent = Decimal('0.00')

        if not errors:
            try:
                room = Room.objects.create(
                    room_number=room_number,
                    block_number=block_number,
                    capacity=capacity,
                    room_rent=room_rent,
                    type=room_type,
                    status=status,
                    image=image
                )
                return redirect(reverse('room_detail', args=[room.room_id]))
            except IntegrityError:
                errors.append('Room number already exists.')
            except Exception as e:
                errors.append(f'Error creating room: {e}')

    # render form (include choices + any errors)
    context = {
        'type_choices': type_choices,
        'status_choices': status_choices,
        'errors': errors,
    }
    return render(request, 'create_room.html', context)



@admin_required
def pending_fees(request):
    # This month's pending students and aggregate
    today = timezone.now().date()
    first = today.replace(day=1)
    last = (first + timedelta(days=31)).replace(day=1) - timedelta(days=1)  # end of month
    # Fees due within this month and unpaid
    fees = Fee.objects.filter(status='Unpaid', due_date__gte=first, due_date__lte=last).select_related('student')
    total_pending_amount = fees.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    students = {f.student for f in fees}
    context = {'fees': fees, 'total_pending_amount': total_pending_amount, 'students': students}
    return render(request, 'pending_fees.html', context)


@admin_required
def mark_transaction_success(request, tx_id):
    tx = get_object_or_404(PaymentTransaction, tx_id=tx_id)
    provider_id = request.POST.get('provider_txn_id') or None
    tx.mark_success(provider_txn_id=provider_id)
    return redirect(reverse('student_detail', args=[tx.student.student_id]))


@admin_required
def export_students_csv(request):
    qs = Student.objects.select_related('room', 'login').all()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="students.csv"'
    writer = csv.writer(response)
    writer.writerow(['student_id', 'name', 'email', 'phone', 'programme', 'district', 'room', 'paid_until', 'is_rent_current'])
    for s in qs:
        writer.writerow([
            s.student_id,
            s.name,
            s.email or '',
            s.phone or '',
            s.programme or '',
            s.district or '',
            s.room.room_number if s.room else '',
            s.paid_until().isoformat() if s.paid_until() else '',
            s.is_rent_current(),
        ])
    return response


@admin_required
def meals_list(request):
    # base queryset
    qs = Meal.objects.all().order_by('-created_at')

    # read filters from querystring
    name = request.GET.get('name', '').strip()
    meal_type = request.GET.get('meal_type', '').strip()
    weekday = request.GET.get('weekday', '').strip()

    if name:
        qs = qs.filter(meal_name__icontains=name)

    if meal_type:
        qs = qs.filter(meal_type=meal_type)

    if weekday != '':
        try:
            weekday_int = int(weekday)
            qs = qs.filter(weekday=weekday_int)
        except ValueError:
            # ignore bad weekday param
            pass

    context = {
        'meals': qs,
        'filter_name': name,
        'filter_meal_type': meal_type,
        'filter_weekday': weekday,
        'MEAL_TYPE': Meal.MEAL_TYPE,
        'WEEKDAYS': [(d.value, d.name.title()) for d in Weekday],
    }
    return render(request, 'meals_list.html', context)


@admin_required
def add_meal(request):
    errors = []
    if request.method == 'POST':
        meal_name = request.POST.get('meal_name', '').strip()
        meal_type = request.POST.get('meal_type', '').strip()
        weekday = request.POST.get('weekday')
        rate = request.POST.get('rate', '').strip()
        meal_pic = request.FILES.get('meal_pic')

        # validations
        if not meal_name:
            errors.append("Meal name is required.")
        if meal_type not in dict(Meal.MEAL_TYPE):
            errors.append("Invalid meal type.")
        try:
            weekday_int = int(weekday)
            if weekday_int not in [d.value for d in Weekday]:
                errors.append("Invalid weekday.")
        except (TypeError, ValueError):
            errors.append("Weekday must be selected.")
        try:
            rate_dec = Decimal(rate)
            if rate_dec < 0:
                errors.append("Rate must be non-negative.")
        except (InvalidOperation, TypeError):
            errors.append("Invalid rate value.")

        if not errors:
            meal = Meal(
                meal_name=meal_name,
                meal_type=meal_type,
                weekday=weekday_int,
                rate=rate_dec
            )
            if meal_pic:
                meal.meal_pic = meal_pic
            meal.save()
            messages.success(request, "Meal added successfully.")
            return redirect(reverse('admin_meals_list'))

    else:
        # defaults for GET
        meal_name = meal_type = ''
        weekday = ''
        rate = ''
        meal_pic = None

    # weekday options for select
    weekday_choices = [(d.value, d.name.title()) for d in Weekday]
    meal_types = Meal.MEAL_TYPE
    return render(request, 'meal_form.html', {
        'action': 'Add',
        'errors': errors,
        'meal': None,
        'meal_name': meal_name,
        'meal_type': meal_type,
        'weekday': weekday,
        'rate': rate,
        'weekday_choices': weekday_choices,
        'meal_types': meal_types,   # <<-- added
    })

@admin_required
def edit_meal(request, pk):
    meal = get_object_or_404(Meal, pk=pk)
    errors = []
    if request.method == 'POST':
        meal_name = request.POST.get('meal_name', '').strip()
        meal_type = request.POST.get('meal_type', '').strip()
        weekday = request.POST.get('weekday')
        rate = request.POST.get('rate', '').strip()
        meal_pic = request.FILES.get('meal_pic')
        remove_pic = request.POST.get('remove_pic') == '1'

        # validations
        if not meal_name:
            errors.append("Meal name is required.")
        if meal_type not in dict(Meal.MEAL_TYPE):
            errors.append("Invalid meal type.")
        try:
            weekday_int = int(weekday)
            if weekday_int not in [d.value for d in Weekday]:
                errors.append("Invalid weekday.")
        except (TypeError, ValueError):
            errors.append("Weekday must be selected.")
        try:
            rate_dec = Decimal(rate)
            if rate_dec < 0:
                errors.append("Rate must be non-negative.")
        except (InvalidOperation, TypeError):
            errors.append("Invalid rate value.")

        if not errors:
            meal.meal_name = meal_name
            meal.meal_type = meal_type
            meal.weekday = weekday_int
            meal.rate = rate_dec
            if meal_pic:
                meal.meal_pic = meal_pic
            elif remove_pic and meal.meal_pic:
                # delete file reference (file will be removed by storage backend if configured)
                meal.meal_pic.delete(save=False)
                meal.meal_pic = None
            meal.save()
            messages.success(request, "Meal updated.")
            return redirect(reverse('admin_meals_list'))
    else:
        meal_name = meal.meal_name
        meal_type = meal.meal_type
        weekday = meal.weekday
        rate = meal.rate

    weekday_choices = [(d.value, d.name.title()) for d in Weekday]
    meal_types = Meal.MEAL_TYPE
    return render(request, 'meal_form.html', {
        'action': 'Edit',
        'errors': errors,
        'meal': meal,
        'meal_name': meal_name,
        'meal_type': meal_type,
        'weekday': weekday,
        'rate': rate,
        'weekday_choices': weekday_choices,
        'meal_types': meal_types,   # <<-- added
    })

@admin_required
@require_http_methods(["POST"])
def delete_meal(request, pk):
    meal = get_object_or_404(Meal, pk=pk)
    # delete file too (optional)
    if meal.meal_pic:
        meal.meal_pic.delete(save=False)
    meal.delete()
    messages.success(request, "Meal deleted.")
    return redirect(reverse('admin_meals_list'))


# ---------- Notifications ----------
@admin_required
def notifications_list(request):
    notifications = Notification.objects.order_by('-created_at')
    return render(request, 'notifications_list.html', {'notifications': notifications})

@admin_required
def add_notification(request):
    errors = []
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        message_text = request.POST.get('message', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        if not title:
            errors.append("Title is required.")
        if not message_text:
            errors.append("Message is required.")

        if not errors:
            note = Notification.objects.create(
                title=title,
                message=message_text,
                is_active=is_active
            )
            messages.success(request, "Notification created.")
            return redirect(reverse('admin_notifications_list'))
    else:
        title = message_text = ''
        is_active = True

    return render(request, 'notification_form.html', {
        'action': 'Add',
        'errors': errors,
        'note': None,
        'title': title,
        'message_text': message_text,
        'is_active': is_active
    })

@admin_required
def edit_notification(request, pk):
    note = get_object_or_404(Notification, pk=pk)
    errors = []
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        message_text = request.POST.get('message', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        if not title:
            errors.append("Title is required.")
        if not message_text:
            errors.append("Message is required.")

        if not errors:
            note.title = title
            note.message = message_text
            note.is_active = is_active
            note.save()
            messages.success(request, "Notification updated.")
            return redirect(reverse('admin_notifications_list'))
    else:
        title = note.title
        message_text = note.message
        is_active = note.is_active

    return render(request, 'notification_form.html', {
        'action': 'Edit',
        'errors': errors,
        'note': note,
        'title': title,
        'message_text': message_text,
        'is_active': is_active
    })

@admin_required
@require_http_methods(["POST"])
def delete_notification(request, pk):
    note = get_object_or_404(Notification, pk=pk)
    note.delete()
    messages.success(request, "Notification deleted.")
    return redirect(reverse('admin_notifications_list'))



import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL_USER = "info.smarthostel@gmail.com"
EMAIL_PASS = "uuhrwszkkugktmhf"

def send_email(to_email: str, subject: str, body: str):
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        
        # Create plain text fallback
        text = """Welcome to Azoria AI! Please enable HTML to view this email."""
        html = body
        
        # Attach both versions
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))
        
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, to_email, msg.as_string())
            
    except smtplib.SMTPException as e:
        print(f"SMTP error sending to {to_email}: {e}")
    except Exception as e:
        print(f"General error sending to {to_email}: {e}")
        
        

OTP_TTL_MINUTES = 10  # OTP expiry

@require_http_methods(["GET", "POST"])
def forgot_password(request):
    if request.method == "GET":
        # Render the forgot password form
        return render(request, "forgot_password.html")

    # POST: process the email and send OTP
    email = request.POST.get("email", "").strip()
    if not email:
        messages.error(request, "Please enter an email address.")
        return redirect("forgot_password")

    student = Student.objects.filter(email__iexact=email).first()
    if not student:
        messages.error(request, "User not found.")
        return redirect("forgot_password")

    # Generate OTP and store in session with creation time and email
    otp = f"{random.randint(100000, 999999)}"
    request.session["otp"] = otp
    request.session["otp_email"] = email
    # store ISO timestamp for JSON-serializable
    request.session["otp_created_at"] = timezone.now().isoformat()

    # Send OTP email (ensure EMAIL settings are configured)
    subject = "OTP for Password Reset"
    body = f"Your OTP is {otp}. It is valid for {OTP_TTL_MINUTES} minutes."
    try:
        send_email(email, subject, body)
    except Exception:
        # Log in real app; here we notify user
        messages.error(request, "Failed to send OTP email. Please try again later.")
        return redirect("forgot_password")

    return redirect("verify_otp")


@require_http_methods(["GET", "POST"])
def verify_otp(request):
    if request.method == "GET":
        return render(request, "verify_otp.html")

    # POST: check provided otp
    submitted_otp = (request.POST.get("otp") or "").strip()
    stored_otp = request.session.get("otp")
    created_iso = request.session.get("otp_created_at")

    if not stored_otp or not created_iso:
        messages.error(request, "Session expired or no OTP found. Please request a new OTP.")
        return redirect("forgot_password")

    # check expiry
    try:
        created_at = timezone.datetime.fromisoformat(created_iso)
        if timezone.is_naive(created_at):
            created_at = timezone.make_aware(created_at, timezone.get_current_timezone())
    except Exception:
        created_at = timezone.now() - timedelta(minutes=OTP_TTL_MINUTES + 1)

    if timezone.now() - created_at > timedelta(minutes=OTP_TTL_MINUTES):
        # clear expired OTP
        request.session.pop("otp", None)
        request.session.pop("otp_email", None)
        request.session.pop("otp_created_at", None)
        messages.error(request, "OTP has expired. Please request a new one.")
        return redirect("forgot_password")

    if submitted_otp != stored_otp:
        messages.error(request, "Invalid OTP. Please try again.")
        return redirect("verify_otp")

    # OTP correct -> allow reset
    # Optionally mark in session that verification passed
    request.session["otp_verified"] = True
    return redirect("reset_password")


@require_http_methods(["GET", "POST"])
def reset_password(request):
    if request.method == "GET":
        # ensure user passed OTP verification
        if not request.session.get("otp_verified"):
            messages.error(request, "You must verify the OTP first.")
            return redirect("forgot_password")
        return render(request, "reset_password.html")

    # POST: save new password
    password = request.POST.get("password", "")
    confirm_password = request.POST.get("confirm_password", "")

    if not password or not confirm_password:
        messages.error(request, "Please fill in both password fields.")
        return redirect("reset_password")

    if password != confirm_password:
        messages.error(request, "Passwords do not match.")
        return redirect("reset_password")

    email = request.session.get("otp_email")
    if not email:
        messages.error(request, "Session expired. Please start the reset flow again.")
        return redirect("forgot_password")

    student = Student.objects.filter(email__iexact=email).first()
    if not student or not getattr(student, "login", None):
        messages.error(request, "User not found or no login associated.")
        return redirect("forgot_password")

    # Hash the password and save onto the related login model
    user_login = student.login
    user_login.password = make_password(password)  # store hashed password
    user_login.save()

    # Clear OTP-related session data
    for k in ("otp", "otp_email", "otp_created_at", "otp_verified"):
        request.session.pop(k, None)

    # Notify user
    subject = "Password Changed Successfully"
    body = "Your password has been successfully updated. You can now log in with your new password."
    try:
        send_email(email, subject, body)
    except Exception:
        pass

    messages.success(request, "Password changed successfully. Please log in.")
    return redirect("login_return") 






@admin_required
@require_http_methods(["GET"])
def admin_complaints_list(request):
    """
    Admin view to list all complaints. Supports optional ?status= filter and ?q= search.
    """
    qs = Complaint.objects.select_related('student', 'room').all()

    status = request.GET.get('status')
    q = request.GET.get('q')
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(description__icontains=q) |
            Q(student__name__icontains=q)
        )

    qs = qs.order_by('-created_at')

    # get choices here
    status_choices = Complaint._meta.get_field('status').choices

    return render(request, 'admin_complaints_list.html', {
        'complaints': qs,
        'status_choices': status_choices,
    })


@admin_required
@require_http_methods(["GET", "POST"])
def admin_complaint_detail(request, pk):
    """
    Admin view for a single complaint. Admin can change status and add a response.
    """
    complaint = get_object_or_404(Complaint, pk=pk)

    if request.method == 'POST':
        # Minimal form handling to update status and admin_response
        new_status = request.POST.get('status')
        admin_response = request.POST.get('admin_response', '').strip()
        changed = False
        if new_status and new_status in dict(Complaint.STATUS_CHOICES).keys():
            complaint.status = new_status
            changed = True
        if admin_response:
            complaint.admin_response = admin_response
            changed = True
        if changed:
            complaint.updated_at = timezone.now()
            complaint.save()
            messages.success(request, "Complaint updated.")
        else:
            messages.info(request, "No changes were made.")
        return redirect(reverse('admin_complaint_detail', kwargs={'pk': complaint.pk}))

    return render(request, 'admin_complaint_detail.html', {'complaint': complaint, 'status_choices': Complaint.STATUS_CHOICES})