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
        'CLIENT_ID': 'test-client-id',
        'CLIENT_SECRET': 'test-secret',
        'REDIRECT_URI': 'http://localhost:8000/callback',
        'S3_BUCKET_NAME': 'test-bucket',
        'AWS_ACCESS_KEY_ID': 'test-access-key',
        'AWS_SECRET_ACCESS_KEY': 'test-secret-key',
        'AWS_REGION': 'test-region',
        'DATABASE_URL': 'postgresql://user:pass@host/db',
        'JWT_SECRET_KEY': 'test-jwt-secret'
    })

    # Reload the config module to apply the mocked environment
    importlib.reload(app.config)
    settings = app.config.settings

    # Assert that the settings were loaded correctly
    assert settings.REDIS_URL == 'redis://mock-redis:6379/0'
    assert settings.CLIENT_ID == 'test-client-id'
    assert settings.CLIENT_SECRET == 'test-secret'
    assert settings.S3_BUCKET_NAME == 'test-bucket'
    assert settings.AWS_ACCESS_KEY_ID == 'test-access-key'
    assert settings.AWS_SECRET_ACCESS_KEY == 'test-secret-key'
    assert settings.AWS_REGION == 'test-region'
    assert settings.DATABASE_URL == 'postgresql://user:pass@host/db'
    assert settings.JWT_SECRET_KEY == 'test-jwt-secret'
