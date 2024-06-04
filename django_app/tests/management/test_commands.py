import uuid
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest import mock

import pytest
import requests
from botocore.exceptions import UnknownClientMethodError
from django.conf import settings
from django.core.management import CommandError, call_command
from django.utils import timezone
from magic_link.models import MagicLink
from redbox_app.redbox_core.models import File, StatusEnum, User
from requests_mock import Mocker

# === show_magiclink_url command tests ===


@pytest.mark.django_db()
def test_command_output_no_such_user():
    # Given

    # When
    with pytest.raises(CommandError) as exception:
        call_command("show_magiclink_url", "alice@example.com")

    # Then
    assert str(exception.value) == "No User found with email alice@example.com"


@pytest.mark.django_db()
def test_command_output_no_links_ever(alice: User):
    # Given

    # When
    with pytest.raises(CommandError) as exception:
        call_command("show_magiclink_url", alice.email)

    # Then
    assert str(exception.value) == f"No MagicLink found for user {alice.email}"


@pytest.mark.django_db()
def test_command_output_no_valid_links(alice: User):
    # Given
    MagicLink.objects.create(user=alice, expires_at=datetime.now(UTC) - timedelta(seconds=10))

    # When
    with pytest.raises(CommandError) as exception:
        call_command("show_magiclink_url", alice.email)

    # Then
    assert str(exception.value) == f"No active link for user {alice.email}"


@pytest.mark.django_db()
def test_command_output_with_valid_links(alice: User):
    # Given
    link: MagicLink = MagicLink.objects.create(user=alice, expires_at=datetime.now(UTC) + timedelta(seconds=10))
    out, err = StringIO(), StringIO()

    # When
    call_command("show_magiclink_url", alice.email, stdout=out, stderr=err)

    # Then
    assert out.getvalue().strip() == link.get_absolute_url()


# === delete_expired_data command tests ===
EXPIRED_FILE_DATE = timezone.now() - timedelta(seconds=(settings.FILE_EXPIRY_IN_SECONDS + 60))


@pytest.mark.parametrize(
    ("mock_datetime", "should_delete"),
    [
        (EXPIRED_FILE_DATE, True),
        (timezone.now(), False),
    ],
)
@pytest.mark.django_db()
def test_delete_expired_data(uploaded_file: File, requests_mock: Mocker, mock_datetime: datetime, should_delete: bool):
    # Given
    mock_file = uploaded_file
    mock_file.last_referenced = mock_datetime
    mock_file.save()

    requests_mock.delete(
        f"http://{settings.CORE_API_HOST}:{settings.CORE_API_PORT}/file/{mock_file.core_file_uuid}",
        status_code=201,
        json={
            "key": mock_file.original_file_name,
            "bucket": settings.BUCKET_NAME,
            "uuid": str(uuid.uuid4()),
        },
    )

    # When
    call_command("delete_expired_data")

    # Then
    is_deleted = File.objects.get(id=mock_file.id).status == StatusEnum.deleted
    assert is_deleted == should_delete


@pytest.mark.django_db()
def test_delete_expired_data_with_api_error(uploaded_file: File, requests_mock: Mocker):
    # Given
    mock_file = uploaded_file
    mock_file.last_referenced = EXPIRED_FILE_DATE
    mock_file.save()

    (
        requests_mock.delete(
            f"http://{settings.CORE_API_HOST}:{settings.CORE_API_PORT}/file/{mock_file.core_file_uuid}",
            exc=requests.exceptions.HTTPError,
        ),
    )

    # When
    call_command("delete_expired_data")

    # Then
    assert File.objects.get(id=mock_file.id).status != StatusEnum.deleted


@pytest.mark.django_db()
def test_delete_expired_data_with_s3_error(uploaded_file: File, requests_mock: Mocker):
    with mock.patch("redbox_app.redbox_core.models.File.delete_from_s3") as s3_mock:
        s3_mock.side_effect = UnknownClientMethodError(method_name="")

        # Given
        mock_file = uploaded_file
        mock_file.last_referenced = EXPIRED_FILE_DATE
        mock_file.save()

        requests_mock.delete(
            f"http://{settings.CORE_API_HOST}:{settings.CORE_API_PORT}/file/{mock_file.core_file_uuid}",
            status_code=201,
            json={
                "key": mock_file.original_file_name,
                "bucket": settings.BUCKET_NAME,
                "uuid": str(uuid.uuid4()),
            },
        )

        # When
        call_command("delete_expired_data")

        # Then
        assert File.objects.get(id=mock_file.id).status != StatusEnum.deleted
