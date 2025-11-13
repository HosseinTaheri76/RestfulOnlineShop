from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from django.utils.translation import gettext as _
from rest_framework.generics import GenericAPIView

from . import serializers


class BaseOTPView(GenericAPIView):
    purpose = None

    def get_channel(self):
        channel = self.kwargs['channel']
        if channel not in ['email', 'phone']:
            raise NotFound(_('Unknown channel specified.'))
        return channel

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({'purpose': self.purpose})
        return context

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class OTPGrantRequestView(BaseOTPView):

    def get_serializer_class(self):
        return {
            'email': serializers.EmailOTPRequestSerializer,
            'phone': serializers.PhoneNumberOTPRequestSerializer,
        }[self.get_channel()]


class OTPGrantConfirmView(BaseOTPView):

    def get_serializer_class(self):
        return {
            'email': serializers.EmailOTPConfirmSerializer,
            'phone': serializers.PhoneNumberOTPConfirmSerializer,
        }[self.get_channel()]
