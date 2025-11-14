from rest_framework import generics, permissions

from . import serializers
from otp.views import OTPRequestView, OTPConfirmView


class UserCreateView(generics.CreateAPIView):
    serializer_class = serializers.UserCreateSerializer


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
