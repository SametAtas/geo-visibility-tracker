#!/usr/bin/env bash
# A real WordPress for tests: WordPress 7.1.3 on SQLite (no MySQL needed), served by PHP's built-in server.
# Usage: tests/wordpress/setup_wordpress.sh [work_dir] [port]
# Then:  GEO_WP_URL=http://127.0.0.1:<port> pytest tests/test_wordpress_live.py
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
WORK="${1:-$REPO/.wp-test}"
PORT="${2:-8899}"
WP_VERSION="${WP_VERSION:-7.1.3}"
SQLITE_VERSION=v2.2.23
SITE="$WORK/site"

mkdir -p "$WORK"
GIT="git -c advice.detachedHead=false"
if [ ! -f "$SITE/wp-includes/version.php" ]; then
  $GIT clone --quiet --depth 1 --branch "$WP_VERSION" https://github.com/WordPress/WordPress "$SITE"
fi
PLUGINS="$SITE/wp-content/plugins"
if [ ! -d "$PLUGINS/sqlite-database-integration" ]; then
  # The plugin lives in a monorepo and links to a sibling package; copy it with the links resolved.
  $GIT clone --quiet --depth 1 --branch "$SQLITE_VERSION" https://github.com/WordPress/sqlite-database-integration "$WORK/sqlite-src"
  cp -rL "$WORK/sqlite-src/packages/plugin-sqlite-database-integration" "$PLUGINS/sqlite-database-integration"
fi
rm -rf "$PLUGINS/geo-signals" && cp -r "$REPO/wordpress-plugin/geo-signals" "$PLUGINS/geo-signals"

# SQLite drop-in: WordPress loads wp-content/db.php instead of its MySQL driver.
sed -e "s#{SQLITE_IMPLEMENTATION_FOLDER_PATH}#$PLUGINS/sqlite-database-integration#" \
    -e "s#{SQLITE_PLUGIN}#sqlite-database-integration/load.php#" \
    "$PLUGINS/sqlite-database-integration/db.copy" > "$SITE/wp-content/db.php"

cat > "$SITE/wp-config.php" <<PHP
<?php
define( 'DB_NAME', 'wordpress' ); define( 'DB_USER', '' ); define( 'DB_PASSWORD', '' ); define( 'DB_HOST', '' );
define( 'DB_CHARSET', 'utf8mb4' ); define( 'DB_COLLATE', '' );
define( 'DB_DIR', '$WORK/db/' ); define( 'DB_FILE', 'wordpress.sqlite' );
define( 'WP_HOME', 'http://127.0.0.1:$PORT' ); define( 'WP_SITEURL', 'http://127.0.0.1:$PORT' );
define( 'WP_ENVIRONMENT_TYPE', 'local' );
define( 'WP_HTTP_BLOCK_EXTERNAL', true );      // tests never call the internet
define( 'AUTOMATIC_UPDATER_DISABLED', true );
define( 'DISABLE_WP_CRON', true );
define( 'WP_DEBUG', true ); define( 'WP_DEBUG_LOG', '$WORK/debug.log' ); define( 'WP_DEBUG_DISPLAY', false );
foreach ( array( 'AUTH_KEY', 'SECURE_AUTH_KEY', 'LOGGED_IN_KEY', 'NONCE_KEY', 'AUTH_SALT', 'SECURE_AUTH_SALT', 'LOGGED_IN_SALT', 'NONCE_SALT' ) as \$k ) {
	define( \$k, 'test-only-' . \$k );
}
\$table_prefix = 'wp_';
if ( ! defined( 'ABSPATH' ) ) { define( 'ABSPATH', __DIR__ . '/' ); }
require_once ABSPATH . 'wp-settings.php';
PHP

rm -rf "$WORK/db" && mkdir -p "$WORK/db"
# Fresh install, then posts. seed.php loads WordPress itself (no server needed for this step).
php "$HERE/seed.php" "$SITE" "$REPO/tests/fixtures/signals_cases.json"

# Serve it. Several workers, because WordPress sometimes calls itself (loopback requests).
pkill -f "php -S 127.0.0.1:$PORT" 2>/dev/null || true
PHP_CLI_SERVER_WORKERS=4 nohup php -S "127.0.0.1:$PORT" -t "$SITE" "$HERE/router.php" > "$WORK/server.log" 2>&1 &
for _ in $(seq 1 50); do
  curl -sf "http://127.0.0.1:$PORT/wp-json/" > /dev/null && break
  sleep 0.2
done
curl -sf "http://127.0.0.1:$PORT/wp-json/geo-signals/v1/summary" && echo
echo "WordPress $WP_VERSION ready at http://127.0.0.1:$PORT (admin / test-password-123)"
