from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from rest_framework.generics import GenericAPIView

from . import serializers


class BaseOTPView(GenericAPIView):
    purpose = None
    valid_channels = ['email', 'phone']

    def serializer_valid(self, serializer):
        pass

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({'purpose': self.purpose})
        return context

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.serializer_valid(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get_channel(self):
        assert len(self.valid_channels) > 0, 'no valid channels specified'
        url_channel = self.kwargs.get('channel')
        if url_channel:
            if url_channel not in self.valid_channels:
                raise NotFound('invalid channel')
            return url_channel
        else:
            if len(self.valid_channels) != 1:
                raise NotFound('more than one valid channel specified but no url channel to select one')
            return self.valid_channels[0]

class OTPRequestView(BaseOTPView):

    def get_serializer_class(self):
        return {
            'email': serializers.EmailOTPRequestSerializer,
            'phone': serializers.PhoneNumberOTPRequestSerializer,
        }[self.get_channel()]


class OTPConfirmView(BaseOTPView):

    create_grant = False

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({'create_grant': self.create_grant})
        return context

    def get_serializer_class(self):
        return {
            'email': serializers.EmailOTPConfirmSerializer,
            'phone': serializers.PhoneNumberOTPConfirmSerializer,
        }[self.get_channel()]
