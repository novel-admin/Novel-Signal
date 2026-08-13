from dataclasses import dataclass

from novel_signal.config import Settings, get_settings
from novel_signal.sources.base import SourceType


@dataclass(frozen=True)
class SourceDefinition:
    source_type: SourceType
    owner: str
    purpose: str
    configured: bool


def source_definitions(settings: Settings | None = None) -> tuple[SourceDefinition, ...]:
    config = settings or get_settings()
    sp_api_configured = all(
        (
            config.amazon_lwa_client_id,
            config.amazon_lwa_client_secret.get_secret_value(),
            config.amazon_lwa_refresh_token.get_secret_value(),
            config.amazon_aws_access_key_id,
            config.amazon_aws_secret_access_key.get_secret_value(),
        )
    )
    ads_configured = all(
        (
            config.amazon_ads_client_id,
            config.amazon_ads_client_secret.get_secret_value(),
            config.amazon_ads_refresh_token.get_secret_value(),
            config.amazon_ads_profile_ids,
        )
    )
    gsc_configured = all(
        (
            config.google_search_console_credentials_json.get_secret_value(),
            config.google_search_console_sites,
        )
    )
    meta_configured = all(
        (
            config.meta_app_id,
            config.meta_app_secret.get_secret_value(),
            config.meta_access_token.get_secret_value(),
            config.meta_ad_account_ids,
        )
    )

    return (
        SourceDefinition(
            SourceType.AMAZON_SP_API,
            "Akanksh",
            "Novel seller data",
            sp_api_configured,
        ),
        SourceDefinition(
            SourceType.AMAZON_BRAND_ANALYTICS,
            "Akanksh",
            "Permitted Amazon keyword reports",
            sp_api_configured,
        ),
        SourceDefinition(
            SourceType.AMAZON_ADS_API,
            "Palguna",
            "Novel advertising data",
            ads_configured,
        ),
        SourceDefinition(
            SourceType.GOOGLE_SEARCH_CONSOLE,
            "Akanksh",
            "Novel-owned search performance",
            gsc_configured,
        ),
        SourceDefinition(
            SourceType.META_MARKETING_API,
            "Palguna",
            "Novel Meta ads",
            meta_configured,
        ),
        SourceDefinition(
            SourceType.META_AD_LIBRARY,
            "Palguna",
            "Supported public competitor ads",
            bool(config.meta_ad_library_access_token.get_secret_value()),
        ),
        SourceDefinition(
            SourceType.AMAZON_PUBLIC_PAGES,
            "Akanksh",
            "Approved public competitor facts",
            True,
        ),
    )
