from django.shortcuts import render

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
from student.models import Fee, PaymentTransaction
from student.views import _get_student_from_session

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
    # For QR/UPI the server might provide a QR payload or UPI URL — here we return a mock UPI deeplink
    upi_deeplink = f"upi://pay?pa=example@upi&pn={student.name.replace(' ','')}&am={amount}&tn=Hostel%20Rent&cu=INR"
    resp = {
        'tx_id': tx.tx_id,
        'amount': str(tx.amount),
        'method': tx.method,
        'upi_deeplink': upi_deeplink,
    }
    return JsonResponse(resp)

@require_POST
def finalize_transaction(request):
    print('ok')
    student = _get_student_from_session(request)
    if not student:
        return HttpResponseForbidden("Not logged in")
    tx_id = request.POST.get('tx_id')
    provider_txn_id = request.POST.get('provider_txn_id')  # optional
    if not tx_id:
        return HttpResponseBadRequest("Missing tx_id")

    tx = PaymentTransaction.objects.filter(tx_id=tx_id, student=student).first()
    if not tx:
        return HttpResponseBadRequest("Invalid transaction")

    # Simulate provider verification here. For production: verify signatures/webhooks.
    # Mark success and compute end_date (mark_success will skip setting start/end for fee-specific txs).
    tx.mark_success(provider_txn_id=provider_txn_id)

    resp = {
        'message': 'Payment recorded (simulated)',
        'tx_id': tx.tx_id,
    }

    # Defensive: tx.meta might be None
    if tx.meta and tx.meta.get('fee_id'):
        fee_id = tx.meta['fee_id']
        fee = Fee.objects.get(fee_id=fee_id, student=student)

        # If transaction start/end are still null for this fee-specific tx,
        # set start_date = fee.created_at.date() and end_date = fee.due_date
        if tx.start_date is None and tx.end_date is None:
            tx.start_date = fee.created_at.date()
            tx.end_date = fee.due_date
            tx.save(update_fields=['start_date', 'end_date', 'updated_at'])

        fee.status = 'Paid'
        fee.payment_date = timezone.now().date()
        fee.note = f'Paid via {tx.method}'
        fee.payment_tx = tx
        fee.save()
        resp['fee_id'] = fee.fee_id
    else:
        # Then create a Fee (Paid) record linked to the tx
        fee = Fee.objects.create(
            student=student,
            amount=tx.amount,
            due_date=tx.start_date or timezone.now().date(),
            status='Paid',
            payment_date=timezone.now().date(),
            note=f'Paid via {tx.method}',
            payment_tx=tx
        )
        resp['fee_id'] = fee.fee_id
        resp['paid_until'] = tx.end_date.isoformat() if tx.end_date else None
        resp['days_left'] = (tx.end_date - timezone.now().date()).days if tx.end_date else None

    return JsonResponse(resp)
