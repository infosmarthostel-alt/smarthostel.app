from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from student import views as sv
from myadmin import views as mv
from payment import views as pv


urlpatterns = [
    path('',mv.index,name='home'),
    path('register', sv.student_register, name='student_register'),
    path('login_post', mv.login_post, name="login_post"),
    path('login_return', mv.login_return, name="login_return"),
    path('logout', mv.logout, name="logout"),
    
    path('admin/dashboard/', mv.admin_dashboard, name='dashboard'),
    path('admin/students/', mv.students_list, name='students_list'),
    path('admin/student/<int:student_id>/', mv.student_detail, name='student_detail'),
    path('admin/student/<int:student_id>/toggle-block/', mv.toggle_block_student, name='toggle_block_student'),
    path('admin/rooms/', mv.rooms_list, name='rooms_list'),
    path('admin/room/create/', mv.create_room, name='create_room'),
    path('admin/room/<int:room_id>/', mv.room_detail, name='room_detail'),
    path('admin/pending-fees/', mv.pending_fees, name='pending_fees'),
    path('admin/export/students-csv/', mv.export_students_csv, name='export_students_csv'),
    # utilities
    path('admin/transaction/<uuid:tx_id>/mark-success/', mv.mark_transaction_success, name='mark_tx_success'),


    path('s_home',sv.s_home,name='s_home'),
    path('profile/', sv.view_profile, name='profile_view'),
    path('profile/edit/', sv.edit_profile, name='profile_edit'),
    path('profile/change-password/', sv.change_password, name='profile_change_password'),
    path('api/room-programme-counts/', sv.room_programme_counts, name='room_programme_counts'),
    
    
    path('student/pay/', pv.payment_page, name='student_pay_page'),
    path('student/create-transaction/', pv.create_transaction, name='create_transaction'),
    path('student/finalize-transaction/', pv.finalize_transaction, name='finalize_transaction'),
    
    # Meals
    path('admin/meals/', mv.meals_list, name='admin_meals_list'),
    path('admin/meals/add/', mv.add_meal, name='admin_add_meal'),
    path('admin/meals/<int:pk>/edit/', mv.edit_meal, name='admin_edit_meal'),
    path('admin/meals/<int:pk>/delete/', mv.delete_meal, name='admin_delete_meal'),

    # Notifications
    path('admin/notifications/', mv.notifications_list, name='admin_notifications_list'),
    path('admin/notifications/add/', mv.add_notification, name='admin_add_notification'),
    path('admin/notifications/<int:pk>/edit/', mv.edit_notification, name='admin_edit_notification'),
    path('admin/notifications/<int:pk>/delete/', mv.delete_notification, name='admin_delete_notification'),

    path('today/', sv.meals_today, name='meals_today'),
    path('notifications/', sv.notifications_list, name='notifications'),
    
    path("forgot-password/", mv.forgot_password, name="forgot_password"),
    path("verify-otp/", mv.verify_otp, name="verify_otp"),
    path("reset-password/", mv.reset_password, name="reset_password"),
    
    path('student/complaint/new/', sv.student_submit_complaint, name='student_submit_complaint'),
    path('student/complaints/', sv.student_complaints_list, name='student_complaints_list'),

    # admin
    path('admin/complaints/', mv.admin_complaints_list, name='admin_complaints_list'),
    path('admin/complaints/<int:pk>/', mv.admin_complaint_detail, name='admin_complaint_detail'),

    
]

if settings.DEBUG: 
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)