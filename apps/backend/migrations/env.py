from logging.config import fileConfig

from alembic import context
from novel_signal.config import get_settings
from novel_signal.db import Base
from novel_signal.modules.actions import models as action_models  # noqa: F401
from novel_signal.modules.ads import models as ads_models  # noqa: F401
from novel_signal.modules.alerts import models as alert_models  # noqa: F401
from novel_signal.modules.auth import models as auth_models  # noqa: F401
from novel_signal.modules.collection import models as collection_models  # noqa: F401
from novel_signal.modules.keywords import models as keyword_models  # noqa: F401
from novel_signal.modules.listings import models as listing_models  # noqa: F401
from novel_signal.modules.market_share import models as market_share_models  # noqa: F401
from novel_signal.modules.price_monitoring import models as price_monitoring_models  # noqa: F401
from novel_signal.modules.rank_visibility import models as rank_visibility_models  # noqa: F401
from novel_signal.modules.reviews import models as review_models  # noqa: F401
from novel_signal.modules.scorecards import models as scorecard_models  # noqa: F401
from novel_signal.modules.universe import models as universe_models  # noqa: F401
from sqlalchemy import engine_from_config, pool

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
