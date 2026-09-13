"""Hard limits for untrusted mail; memory limits apply to the Linux sync worker."""
import sys

MAX_MESSAGE_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_DECODED_BYTES = 10 * 1024 * 1024
MAX_MIME_PARTS = 100
MAX_ATTACHMENTS = 10
MAX_PDF_PAGES = 40
MAX_PDF_STREAM_BYTES = 2 * 1024 * 1024
MAX_PDF_TEXT_CHARS = 60000
MAX_SYNC_MAILS = 2000
MAX_BATCH_BYTES = 64 * 1024 * 1024
WORKER_MEMORY_BYTES = 768 * 1024 * 1024


def apply_worker_limits():
    if sys.platform.startswith("linux"):
        import resource
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = WORKER_MEMORY_BYTES if hard == resource.RLIM_INFINITY else min(hard, WORKER_MEMORY_BYTES)
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
