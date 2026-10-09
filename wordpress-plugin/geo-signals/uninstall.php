<?php
/**
 * Removing the plugin removes the signals it cached in post meta. Nothing else is stored.
 *
 * @package GeoSignals
 */

defined( 'WP_UNINSTALL_PLUGIN' ) || exit;

delete_post_meta_by_key( '_geo_signals' );
