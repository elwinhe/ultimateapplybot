"""
tests/test_config.py
"""
import importlib
import app.config

def test_settings_load_from_environment(mocker):
    """Tests that the Settings model correctly loads variables from os.environ."""
    # Mock environment variables
    mocker.patch.dict('os.environ', {
        'REDIS_URL': 'redis://mock-redis:6379/0',
        'TENANT_ID': 'test-tenant-id',
        'CLIENT_ID': 'test-client-id',
        'CLIENT_SECRET': 'test-secret',
        'S3_BUCKET_NAME': 'test-bucket',
        'AWS_ACCESS_KEY_ID': 'test-access-key',
        'AWS_SECRET_ACCESS_KEY': 'test-secret-key',
        'AWS_REGION': 'test-region'
    })

    importlib.reload(app.config)
    settings = app.config.settings

    assert settings.REDIS_URL == 'redis://mock-redis:6379/0'
    assert settings.TENANT_ID == 'test-tenant-id'
    assert settings.CLIENT_ID == 'test-client-id'
    assert settings.CLIENT_SECRET == 'test-secret'
    assert settings.S3_BUCKET_NAME == 'test-bucket'
    assert settings.AWS_ACCESS_KEY_ID == 'test-access-key'
    assert settings.AWS_SECRET_ACCESS_KEY == 'test-secret-key'
    assert settings.AWS_REGION == 'test-region'
