<?php
/**
 * GEO signals for one post's HTML. Plain PHP with no WordPress calls, so it can be tested on its own.
 *
 * The rules are the same as geo_tracker/audit.py in the Python package. tests/fixtures/signals_cases.json
 * holds shared test cases, and both the Python tests and tests/php/test_signals.php must pass on them.
 *
 * Patterns use (*UCP) so that \d and \s behave like Python's (Unicode digits and spaces such as U+3000).
 *
 * @package GeoSignals
 */

/** A number with a unit. Years such as "2025 年" are dates, not statistics. */
const GEO_SIGNALS_STAT_RE = '/(*UCP)(?<![\d.])(?!(?:19|20)\d\d\s*年)\d[\d,]*(?:\.\d+)?\s*(?:%|％|萬|億|倍|元|美元|人|次|年)/u';
const GEO_SIGNALS_FAQ_RE  = '/(*UCP)FAQ|常見問題|Q\s*&\s*A/iu';
const GEO_SIGNALS_HREF_RE = '/href=["\'](https?:\/\/[^"\']+)["\']/i';
const GEO_SIGNALS_HEAD_RE = '/<h[23][^>]*>([\s\S]*?)<\/h[23]>/i';

/**
 * HTML to plain text: drop scripts and styles, drop tags, decode a few entities, collapse whitespace.
 */
function geo_signals_strip_html( string $html ): string {
	$html = preg_replace( '/<(script|style)\b[\s\S]*?<\/\1>/i', ' ', $html );
	$text = preg_replace( '/<[^>]+>/', ' ', $html );
	$text = strtr(
		$text,
		array(
			'&nbsp;' => ' ',
			'&amp;'  => '&',
			'&lt;'   => '<',
			'&gt;'   => '>',
			'&quot;' => '"',
			'&#039;' => "'",
		)
	);
	return trim( preg_replace( '/(*UCP)\s+/u', ' ', $text ) );
}

/**
 * 'https://www.Example.com/a?b' -> 'example.com'. Empty string if not a URL.
 */
function geo_signals_host( string $url ): string {
	if ( ! preg_match( '/^https?:\/\/([^\/?#:\s]+)/i', trim( $url ), $m ) ) {
		return '';
	}
	$host = strtolower( $m[1] );
	return 0 === strpos( $host, 'www.' ) ? substr( $host, 4 ) : $host;
}

/**
 * Signals for one post. $own_host is the blog's own domain: links to it (or its subdomains) are not "sources".
 *
 * @return array{chars:int, headings:int, has_faq:bool, external_sources:int, statistics:int, quotes:int, tables:int}
 */
function geo_signals_compute( string $html, string $own_host ): array {
	$text = geo_signals_strip_html( $html );
	$own  = geo_signals_host( 'https://' . $own_host );

	preg_match_all( GEO_SIGNALS_HEAD_RE, $html, $heads );
	$has_faq = false;
	foreach ( $heads[1] as $heading ) {
		if ( preg_match( GEO_SIGNALS_FAQ_RE, geo_signals_strip_html( $heading ) ) ) {
			$has_faq = true;
			break;
		}
	}

	preg_match_all( GEO_SIGNALS_HREF_RE, $html, $links );
	$hosts = array();
	foreach ( $links[1] as $url ) {
		$host = geo_signals_host( $url );
		$mine = $host === $own || substr( $host, -strlen( '.' . $own ) ) === '.' . $own;   // subdomains count as own
		if ( '' !== $host && ! $mine ) {
			$hosts[ $host ] = true;
		}
	}

	return array(
		'chars'            => mb_strlen( preg_replace( '/(*UCP)\s/u', '', $text ), 'UTF-8' ),  // Chinese has no spaces
		'headings'         => count( $heads[1] ),
		'has_faq'          => $has_faq,
		'external_sources' => count( $hosts ),
		'statistics'       => preg_match_all( GEO_SIGNALS_STAT_RE, $text ),
		'quotes'           => preg_match_all( '/<blockquote/i', $html ) + mb_substr_count( $text, '「', 'UTF-8' ),
		'tables'           => preg_match_all( '/<table/i', $html ),
	);
}

/**
 * Whole days between a UTC 'Y-m-d H:i:s' timestamp and now (UTC), rounded down like Python's timedelta.days.
 */
function geo_signals_days_since( string $gmt_datetime, ?int $now = null ): int {
	$then = strtotime( $gmt_datetime . ' UTC' );
	return (int) floor( ( ( $now ?? time() ) - $then ) / 86400 );
}
