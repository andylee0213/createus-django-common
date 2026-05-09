from django.http import Http404
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from datetime import datetime, time

from rest_framework import status
from rest_framework.response import Response
from rest_framework.request import clone_request


class DateFilterMixin:
    date_field = "created_at"

    def _convert_with_user(self, date_str: str, end_of_day: bool = False):
        user = getattr(self.request, "user", None)
        fn = getattr(user, "convert_date_str_to_user_timezone", None)
        if callable(fn):
            return fn(date_str, end_of_day=end_of_day)
        return None

    def _parse_fallback(self, date_str: str, end_of_day: bool = False):
        dt = parse_datetime(date_str)
        if dt is not None:
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt

        d = parse_date(date_str)
        if d is not None:
            dt2 = datetime.combine(d, time.max if end_of_day else time.min)
            return timezone.make_aware(dt2, timezone.get_current_timezone())

        return None

    def filter_queryset_by_date(self, queryset):
        start_date_str = self.request.query_params.get("start_date")
        end_date_str = self.request.query_params.get("end_date")

        start_date = None
        end_date = None

        if start_date_str:
            start_date = self._convert_with_user(start_date_str, end_of_day=False) or self._parse_fallback(start_date_str, end_of_day=False)

        if end_date_str:
            end_date = self._convert_with_user(end_date_str, end_of_day=True) or self._parse_fallback(end_date_str, end_of_day=True)

        if start_date:
            queryset = queryset.filter(**{f"{self.date_field}__gte": start_date})
        if end_date:
            queryset = queryset.filter(**{f"{self.date_field}__lte": end_date})

        return queryset


class CreateListModelMixin:
    def get_serializer(self, *args, **kwargs):
        if isinstance(kwargs.get("data", {}), list):
            kwargs["many"] = True
        return super().get_serializer(*args, **kwargs)


class UserBoundModelMixin:
    user_field = "user"

    def get_user_field(self):
        return self.user_field

    def get_queryset(self):
        return super().get_queryset().filter(**{self.get_user_field(): self.request.user})

    def perform_create(self, serializer):
        serializer.save(**{self.get_user_field(): self.request.user})


class AllowPUTAsCreateMixin:
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object_or_none()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        if instance is None:
            lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
            lookup_value = self.kwargs[lookup_url_kwarg]
            extra_kwargs = {self.lookup_field: lookup_value}
            self.perform_create(serializer, **extra_kwargs)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        self.perform_update(serializer)
        return Response(serializer.data)

    def perform_create(self, serializer, **kwargs):
        serializer.save(**kwargs)

    def perform_update(self, serializer):
        serializer.save()

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def get_object_or_none(self):
        try:
            return self.get_object()
        except Http404:
            if self.request.method == "PUT":
                self.check_permissions(clone_request(self.request, "POST"))
                return None
            raise
