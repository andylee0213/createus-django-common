# filename: createus_common/messaging/views.py

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


class BaseThreadMessageListView(APIView):
    """
    Base view for listing and creating thread messages.

    Subclasses MUST implement:
        get_queryset(request, **kwargs)       -> QuerySet
        get_serializer_class()                -> Serializer class
        get_sender_role(request)              -> int  (SenderRole value)
        check_thread_permission(request, **kwargs) -> None  (raise PermissionDenied if needed)

    Subclasses MAY implement:
        get_thread(request, **kwargs)         -> thread instance (used for timestamp updates etc.)
        handle_attachment(instance, request, **kwargs) -> None  (process uploaded files)
        handle_post_save(instance, request, **kwargs)  -> None  (any post-creation side effects)

    GET  supports ?last_id= for incremental polling.
    POST creates a message, then calls handle_attachment and handle_post_save.
    """

    def get_queryset(self, request, **kwargs):
        raise NotImplementedError

    def get_serializer_class(self):
        raise NotImplementedError

    def get_sender_role(self, request):
        raise NotImplementedError

    def check_thread_permission(self, request, **kwargs):
        pass

    def get_thread(self, request, **kwargs):
        raise NotImplementedError

    def handle_attachment(self, instance, request, **kwargs):
        raise NotImplementedError

    def handle_post_save(self, instance, request, **kwargs):
        pass

    def get_save_kwargs(self, request, **kwargs):
        """Additional keyword arguments passed to serializer.save().

        Override to inject project-specific FK references (e.g. thread, case)
        that the abstract model cannot know about.
        """
        return {}

    def get(self, request, **kwargs):
        self.check_thread_permission(request, **kwargs)
        last_id = request.query_params.get("last_id")
        qs = self.get_queryset(request, **kwargs)
        if last_id:
            qs = qs.filter(id__gt=last_id)
        serializer_class = self.get_serializer_class()
        serializer = serializer_class(qs, many=True)
        return Response(serializer.data)

    def post(self, request, **kwargs):
        self.check_thread_permission(request, **kwargs)
        serializer_class = self.get_serializer_class()
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(
            sender=request.user,
            sender_role=self.get_sender_role(request),
            **self.get_save_kwargs(request, **kwargs),
        )
        self.handle_post_save(instance, request, **kwargs)
        return Response(serializer_class(instance).data, status=status.HTTP_201_CREATED)
