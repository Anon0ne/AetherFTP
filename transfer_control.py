"""Cooperative cancellation shared by workers and folder planning."""


class OperationCancelled(Exception):
    pass


def check_cancelled(event):
    if event is not None and event.is_set():
        raise OperationCancelled('Operation stopped by user')
