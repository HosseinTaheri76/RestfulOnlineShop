from django.db import transaction
from rest_framework import status
from rest_framework import generics, permissions
from rest_framework.response import Response

from . import serializers
from otp.permissions import OTPGrantRequired
from otp.views import OTPRequestView, OTPConfirmView


class UserCreateView(generics.CreateAPIView):
    serializer_class = serializers.UserCreateSerializer


class PasswordLoginView(generics.CreateAPIView):
    serializer_class = serializers.PasswordLoginSerializer

    def perform_create(self, serializer):
        pass


class OTPLoginRequestView(OTPRequestView):
    purpose = 'login'
    valid_channels = ['email', 'phone']


class OTPLoginConfirmView(generics.CreateAPIView):
    serializer_class = serializers.OTPLoginConfirmSerializer

    def perform_create(self, serializer):
        pass


class EmailVerificationRequestView(OTPRequestView):
    valid_channels = ['email']
    purpose = 'email-verification'


class EmailVerificationConfirmView(OTPConfirmView):
    valid_channels = ['email']
    purpose = 'email-verification'

    def serializer_valid(self, serializer):
        user = serializer.instance.user
        user.email_verified = True
        user.save(update_fields=['email_verified'])


class PhoneVerificationRequestView(OTPRequestView):
    valid_channels = ['phone']
    purpose = 'phone-verification'


class PhoneVerificationConfirmView(OTPConfirmView):
    valid_channels = ['phone']
    purpose = 'phone-verification'

    def serializer_valid(self, serializer):
        user = serializer.instance.user
        user.phone_number_verified = True
        user.save(update_fields=['phone_number_verified'])


class RequestPhoneChangeView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, ]
    serializer_class = serializers.RequestPhoneChangeSerializer

    def perform_create(self, serializer):
        pass


class ConfirmPhoneChangeView(OTPConfirmView):
    valid_channels = ['phone']
    purpose = 'change-phone'
    permission_classes = [permissions.IsAuthenticated, ]

    def serializer_valid(self, serializer):
        user = self.request.user
        phone = serializer.instance.phone_number
        user.phone_number = phone
        user.phone_number_verified = True
        user.save(update_fields=['phone_number', 'phone_number_verified'])


class RequestEmailChangeView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, ]
    serializer_class = serializers.RequestEmailChangeSerializer

    def perform_create(self, serializer):
        pass


class ConfirmEmailChangeView(OTPConfirmView):
    valid_channels = ['email']
    purpose = 'change-email'
    permission_classes = [permissions.IsAuthenticated, ]

    def serializer_valid(self, serializer):
        user = self.request.user
        email = serializer.instance.email
        user.email = email
        user.email_verified = True
        user.save(update_fields=['email', 'email_verified'])


class PasswordResetRequestView(OTPRequestView):
    valid_channels = ['email', 'phone']
    purpose = 'reset-password'


class PasswordResetConfirmView(OTPConfirmView):
    valid_channels = ['email', 'phone']
    purpose = 'reset-password'
    create_grant = True


class PasswordResetCompleteView(generics.GenericAPIView):
    purpose = 'reset-password'
    permission_classes = [OTPGrantRequired, ]
    serializer_class = serializers.PasswordResetSerializer

    def post(self, request, *args, **kwargs):
        grant = self.grant
        serializer = self.get_serializer(grant.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
            grant.consume()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PasswordChangeView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated, ]
    serializer_class = serializers.PasswordChangeSerializer

    def get_object(self):
        return self.request.user
