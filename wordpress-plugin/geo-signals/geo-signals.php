<?php
/**
 * Plugin Name:       GEO Signals
 * Description:       Shows, for every post, the signals research links to visibility in AI answers (cited sources, statistics, quotations, FAQ, freshness). Adds a column to the Posts screen and a read-only REST endpoint for automation tools such as n8n.
 * Version:           0.1.0
 * Requires at least: 6.5
 * Requires PHP:      8.1
 * Author:            SametAtas
 * License:           MIT
 * Text Domain:       geo-signals
 *
 * @package GeoSignals
 */

defined( 'ABSPATH' ) || exit;

require_once __DIR__ . '/includes/signals.php';

const GEO_SIGNALS_VERSION  = '0.1.0';
const GEO_SIGNALS_META_KEY = '_geo_signals';

/**
 * Signals for a post, from the cached post meta when it is current, otherwise computed and cached.
 * They are computed from the rendered content (the same HTML the REST API returns as content.rendered).
 */
function geo_signals_for_post( WP_Post $post ): array {
	$cached = get_post_meta( $post->ID, GEO_SIGNALS_META_KEY, true );
	if ( is_array( $cached ) && ( $cached['version'] ?? '' ) === GEO_SIGNALS_VERSION
		&& ( $cached['modified_gmt'] ?? '' ) === $post->post_modified_gmt ) {
		return $cached;
	}
	$html    = apply_filters( 'the_content', $post->post_content );
	$signals = geo_signals_compute( $html, (string) wp_parse_url( home_url(), PHP_URL_HOST ) );
	$signals = array_merge(
		$signals,
		array(
			'version'      => GEO_SIGNALS_VERSION,
			'modified_gmt' => $post->post_modified_gmt,
		)
	);
	update_post_meta( $post->ID, GEO_SIGNALS_META_KEY, $signals );
	return $signals;
}

/** Recompute when a post is saved (not for autosaves or revisions). */
add_action(
	'save_post_post',
	static function ( int $post_id, WP_Post $post ): void {
		if ( wp_is_post_autosave( $post_id ) || wp_is_post_revision( $post_id ) ) {
			return;
		}
		delete_post_meta( $post_id, GEO_SIGNALS_META_KEY );
		if ( 'publish' === $post->post_status ) {
			geo_signals_for_post( $post );
		}
	},
	10,
	2
);

/* ---------------------------------------------------------------- Posts screen column */

add_filter(
	'manage_post_posts_columns',
	static function ( array $columns ): array {
		$columns['geo_signals'] = esc_html__( 'GEO signals', 'geo-signals' );
		return $columns;
	}
);

add_action(
	'manage_post_posts_custom_column',
	static function ( string $column, int $post_id ): void {
		if ( 'geo_signals' !== $column ) {
			return;
		}
		$post = get_post( $post_id );
		if ( ! $post || 'publish' !== $post->post_status ) {
			echo '&mdash;';
			return;
		}
		$s     = geo_signals_for_post( $post );
		$parts = array(
			/* translators: %d: number of external domains linked */
			sprintf( __( 'Sources %d', 'geo-signals' ), $s['external_sources'] ),
			/* translators: %d: number of statistics */
			sprintf( __( 'Stats %d', 'geo-signals' ), $s['statistics'] ),
			/* translators: %d: number of quotations */
			sprintf( __( 'Quotes %d', 'geo-signals' ), $s['quotes'] ),
			$s['has_faq'] ? __( 'FAQ', 'geo-signals' ) : __( 'No FAQ', 'geo-signals' ),
		);
		$style = 0 === $s['external_sources'] ? ' style="color:#b32d2e"' : '';   // no cited source: the first thing to fix
		echo '<span' . $style . '>' . esc_html( implode( ' · ', $parts ) ) . '</span>';  // phpcs:ignore WordPress.Security.EscapeOutput -- $style is a fixed string
	},
	10,
	2
);

/* ---------------------------------------------------------------- REST API (read-only) */

/**
 * GET /wp-json/geo-signals/v1/posts?per_page=20&page=1
 * Published posts with their signals. Sends X-WP-Total and X-WP-TotalPages like the core endpoints,
 * so the same pagination logic (n8n, the Python client) works unchanged.
 * Public on purpose: it only exposes numbers derived from content that /wp/v2/posts already publishes.
 */
function geo_signals_rest_posts( WP_REST_Request $request ): WP_REST_Response {
	$query = new WP_Query(
		array(
			'post_type'      => 'post',
			'post_status'    => 'publish',
			'posts_per_page' => $request['per_page'],
			'paged'          => $request['page'],
			'orderby'        => 'ID',
			'order'          => 'ASC',
		)
	);
	$items = array();
	foreach ( $query->posts as $post ) {
		$s       = geo_signals_for_post( $post );
		$items[] = array(
			'id'                => $post->ID,
			'title'             => get_the_title( $post ),
			'link'              => get_permalink( $post ),
			'modified_gmt'      => $post->post_modified_gmt,
			'days_since_update' => geo_signals_days_since( $post->post_modified_gmt ),
			'signals'           => array_diff_key( $s, array_flip( array( 'version', 'modified_gmt' ) ) ),
		);
	}
	$response = new WP_REST_Response( $items );
	$response->header( 'X-WP-Total', (string) $query->found_posts );
	$response->header( 'X-WP-TotalPages', (string) max( 1, (int) $query->max_num_pages ) );
	return $response;
}

/**
 * GET /wp-json/geo-signals/v1/summary
 * The blog in one object: how many posts cite a source, have 3+ statistics, quotes, an FAQ, a recent update.
 */
function geo_signals_rest_summary(): WP_REST_Response {
	$ids = get_posts(
		array(
			'post_type'      => 'post',
			'post_status'    => 'publish',
			'posts_per_page' => -1,
			'fields'         => 'ids',
		)
	);
	$n = count( $ids );
	if ( 0 === $n ) {
		return new WP_REST_Response( array( 'posts' => 0 ) );
	}
	$count = array_fill_keys( array( 'source', 'stats3', 'quotes', 'faq', 'recent' ), 0 );
	$chars = array();
	foreach ( $ids as $id ) {
		$post = get_post( $id );
		$s    = geo_signals_for_post( $post );
		$count['source'] += $s['external_sources'] > 0 ? 1 : 0;
		$count['stats3'] += $s['statistics'] >= 3 ? 1 : 0;
		$count['quotes'] += $s['quotes'] > 0 ? 1 : 0;
		$count['faq']    += $s['has_faq'] ? 1 : 0;
		$count['recent'] += geo_signals_days_since( $post->post_modified_gmt ) <= 180 ? 1 : 0;
		$chars[]          = $s['chars'];
	}
	sort( $chars );
	$pct = static fn( int $k ): string => round( $k / $n * 100, 0, PHP_ROUND_HALF_EVEN ) . '%';   // same rounding as Python's format()
	return new WP_REST_Response(
		array(
			'posts'                    => $n,
			'median_chars'             => $chars[ intdiv( $n, 2 ) ],
			'with_any_external_source' => $pct( $count['source'] ),
			'with_3plus_statistics'    => $pct( $count['stats3'] ),
			'with_quotes'              => $pct( $count['quotes'] ),
			'with_faq_section'         => $pct( $count['faq'] ),
			'updated_in_last_180_days' => $pct( $count['recent'] ),
		)
	);
}

add_action(
	'rest_api_init',
	static function (): void {
		register_rest_route(
			'geo-signals/v1',
			'/posts',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => 'geo_signals_rest_posts',
				'permission_callback' => '__return_true',
				'args'                => array(
					'per_page' => array(
						'type'    => 'integer',
						'default' => 20,
						'minimum' => 1,
						'maximum' => 100,
					),
					'page'     => array(
						'type'    => 'integer',
						'default' => 1,
						'minimum' => 1,
					),
				),
			)
		);
		register_rest_route(
			'geo-signals/v1',
			'/summary',
			array(
				'methods'             => WP_REST_Server::READABLE,
				'callback'            => 'geo_signals_rest_summary',
				'permission_callback' => '__return_true',
			)
		);
	}
);
