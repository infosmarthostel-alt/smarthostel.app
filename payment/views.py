from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
from django.shortcuts import redirect, render
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
import json
from django.conf import settings
from django.views.decorators.http import require_POST,require_GET
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils import timezone
import hmac, hashlib
from django.urls import reverse
from myadmin.views import send_email
from student.models import Fee, PaymentTransaction
from student.views import _get_student_from_session


def send_payment_success_email(student, transaction, fee, paid_until=None, days_left=None):
    subject = "Payment Successful - SmartHostel"

    room_rent = student._room_rent_or_default()
    room_no = student.room.room_number if student.room else "N/A"
    building = student.room.block_number if student.room else "SmartHostel "

    # Dynamic period text
    if paid_until:
        period_text = f"{transaction.start_date.strftime('%d %b %Y')} – {paid_until.strftime('%d %b %Y')}"
        validity_text = f"Your room access is now valid until <strong>{paid_until.strftime('%d %B %Y')}</strong> ({days_left} days remaining)"
    else:
        period_text = "One-time Fee / Charge"
        validity_text = "Thank you for your payment!"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Payment Receipt - SmartHostel</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background:#f4f6f9; margin:0; padding:0; }}
            .container {{ max-width: 600px; margin: 30px auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }}
            .header {{ background: linear-gradient(135deg, #6366f1, #8b5cf6); color: white; padding: 40px 30px; text-align: center; }}
            .header h1 {{ margin:0; font-size: 28px; font-weight: 600; }}
            .header p {{ margin:10px 0 0; opacity: 0.9; font-size: 16px; }}
            .success-icon {{ font-size: 60px; margin-bottom: 15px; }}
            .content {{ padding: 40px 30px; color: #333; }}
            .highlight-box {{ background: #f0f7ff; border-left: 5px solid #3b82f6; padding: 20px; border-radius: 8px; margin: 25px 0; }}
            table {{ width: 100%; border-collapse: collapse; margin: 25px 0; }}
            td {{ padding: 12px 0; }}
            .label {{ font-weight: 600; color: #555; width: 40%; }}
            .value {{ color: #000; }}
            .amount {{ font-size: 28px; font-weight: bold; color: #10b981; }}
            .footer {{ background: #1f2937; color: #9ca3af; padding: 30px; text-align: center; font-size: 14px; }}
            .btn {{ display: inline-block; background: #6366f1; color: white; padding: 12px 28px; text-decoration: none; border-radius: 8px; margin: 20px 0; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="success-icon">Payment Successful</div>
                <h1>Payment Received!</h1>
                <p>Thank you, <strong>{student.name}</strong>, your payment has been processed successfully.</p>
            </div>

            <div class="content">
                <div class="highlight-box">
                    <p style="margin:0; font-size:18px;">
                        <strong>₹{transaction.amount}</strong> paid successfully on {timezone.now().strftime('%d %B %Y')}
                    </p>
                </div>

                <table>
                    <tr>
                        <td class="label">Student Name</td>
                        <td class="value">{student.name}</td>
                    </tr>
                    <tr>
                        <td class="label">Room Number</td>
                        <td class="value">{room_no}</td>
                    </tr>
                    <tr>
                        <td class="label">Payment For</td>
                        <td class="value">Monthly Hostel Rent</td>
                    </tr>
                    <tr>
                        <td class="label">Covered Period</td>
                        <td class="value">{period_text}</td>
                    </tr>
                    <tr>
                        <td class="label">Payment Method</td>
                        <td class="value">{transaction.get_method_display()}</td>
                    </tr>
                    <tr>
                        <td class="label">Transaction ID</td>
                        <td class="value"><code>{str(transaction.tx_id)[:16]}...</code></td>
                    </tr>
                </table>

                <div style="background:#ecfdf5;padding:20px;border-radius:8px;border:1px solid #bbf7d0;margin:30px 0;text-align:center;">
                    <p style="margin:0;font-size:16px;color:#065f46;">
                        {validity_text}
                    </p>
                </div>

                <p style="text-align:center;">
                    <a href="https://smarthostel-app.onrender.com/login_return" class="btn">View Dashboard</a>
                </p>

                <p>If you have any questions, feel free to contact the admin.</p>
            </div>

            <div class="footer">
                <p><strong>SmartHostel</strong><br>
                {building} • Powered by SmartHostel</p>
                <p style="margin-top:15px;font-size:12px;">This is an automated receipt • Do not reply</p>
            </div>
        </div>
    </body>
    </html>
    """

    send_email(
        to_email=student.email,
        subject=subject,
        body=html_body
    )

    # Optional: Send to parent too
    if student.parent_email:
        send_email(
            to_email=student.parent_email,
            subject=f"Your ward {student.name} has paid hostel rent",
            body=html_body.replace("Payment Received!", "Your Ward's Payment Received!")
                  .replace("Thank you,", f"Hello {student.parent_name or 'Parent'},<br>Thank you for your support!")
        )

@require_GET
def payment_page(request):
    student = _get_student_from_session(request)
    if not student:
        return redirect('/login')
    # Fetch unpaid fees for the student
    unpaid_fees = student.fees.filter(status='Unpaid')
    context = {
        'student': student,
        'room_rent': student._room_rent_or_default(),
        'unpaid_fees': unpaid_fees,  # Add unpaid fees to context
    }
    return render(request, 'payment_page.html', context)

@csrf_exempt
@require_POST
def mark_upi_paid(request):
    import json
    data = json.loads(request.body)
    tx_id = data.get('tx_id')
    try:
        tx = PaymentTransaction.objects.get(tx_id=tx_id)
        tx.status = 'Paid'        # or whatever your field is
        tx.paid_at = timezone.now()
        if tx.fee:
            tx.fee.status = 'Paid'
            tx.fee.save()
        tx.save()
        return JsonResponse({'status': 'success'})
    except PaymentTransaction.DoesNotExist:
        return JsonResponse({'status': 'error'}, status=400)

def upi_processing(request):
    tx_id = request.GET.get('tx_id')
    name = request.GET.get('name', 'Student')
    amount = request.GET.get('amount', '0')

    # Optional: validate tx exists and belongs to user
    tx = get_object_or_404(PaymentTransaction, tx_id=tx_id)

    return render(request, 'upi_processing.html', {
        'tx_id': tx_id,
        'name': name,
        'amount': amount,
    })

from django.utils.http import urlencode

@require_POST
def create_transaction(request):
    """
    Called when the user chooses a method and clicks pay; returns tx_id and data for client.
    """
    student = _get_student_from_session(request)
    if not student:
        return HttpResponseForbidden("Not logged in")

    method = request.POST.get('method', 'upi')
    raw_amount = request.POST.get('amount')
    fee_id = request.POST.get('fee_id')
    fee = None
    if fee_id:
        try:
            fee = Fee.objects.get(fee_id=fee_id, student=student, status='Unpaid')
        except Fee.DoesNotExist:
            return HttpResponseBadRequest("Invalid fee")

    try:
        amount = Decimal(raw_amount) if raw_amount else student._room_rent_or_default()
    except Exception:
        return HttpResponseBadRequest("Invalid amount")

    tx = student.create_initiated_transaction(method=method, amount=amount, meta={'ip': request.META.get('REMOTE_ADDR')}, fee=fee)

    processing_url = reverse('upi_processing') + '?' + urlencode({
        'tx_id': tx.tx_id,
        'name': student.name.split()[0],  # first name
        'amount': str(amount)
    })
    print("here",processing_url)

    resp = {
        'tx_id': tx.tx_id,
        'amount': str(tx.amount),
        'method': tx.method,
        'upi_deeplink': processing_url,   # ← frontend will go here instead of upi:// link
    }
    return JsonResponse(resp)

@require_POST
def finalize_transaction(request):
    student = _get_student_from_session(request)
    if not student:
        return HttpResponseForbidden("Not logged in")

    tx_id = request.POST.get('tx_id')
    provider_txn_id = request.POST.get('provider_txn_id')

    if not tx_id:
        return HttpResponseBadRequest("Missing tx_id")

    tx = PaymentTransaction.objects.filter(tx_id=tx_id, student=student).first()
    if not tx:
        return HttpResponseBadRequest("Invalid transaction")

    tx.mark_success(provider_txn_id=provider_txn_id)

    fee = None
    paid_until = None
    days_left = None

    if tx.meta and tx.meta.get('fee_id'):
        fee_id = tx.meta['fee_id']
        fee = Fee.objects.get(fee_id=fee_id, student=student)
        fee.status = 'Paid'
        fee.payment_date = timezone.now().date()
        fee.note = f'Paid via {tx.get_method_display()} (Tx: {tx.tx_id})'
        fee.payment_tx = tx
        fee.save()
    else:

        due_date = tx.end_date or (timezone.now().date() + timedelta(days=30))
        fee = Fee.objects.create(
            student=student,
            amount=tx.amount,
            due_date=due_date,
            status='Paid',
            payment_date=timezone.now().date(),
            note=f'Monthly Rent Paid via {tx.get_method_display()}',
            payment_tx=tx
        )
        paid_until = tx.end_date
        days_left = (tx.end_date - timezone.now().date()).days if tx.end_date else None

    if student.email:
        send_payment_success_email(student, tx, fee, paid_until, days_left)

    return JsonResponse({
        'message': 'Payment successful! Receipt sent to your email.',
        'tx_id': str(tx.tx_id),
        'fee_id': fee.fee_id if fee else None,
        'paid_until': paid_until.isoformat() if paid_until else None,
        'days_left': days_left,
    })