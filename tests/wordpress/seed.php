<?php
/**
 * Install WordPress and create test posts. Usage: php seed.php <site_dir> <signals_cases.json>
 *
 * Posts: the shared fixture cases (same HTML the unit tests use), a block-editor post, an old post,
 * a draft (must not appear anywhere), and filler posts so the REST API has 3 pages at per_page=10.
 */
define( 'WP_INSTALLING', true );
$_SERVER['HTTP_HOST'] = '127.0.0.1';
require $argv[1] . '/wp-load.php';
require_once ABSPATH . 'wp-admin/includes/upgrade.php';
require_once ABSPATH . 'wp-admin/includes/plugin.php';

add_filter( 'pre_wp_mail', '__return_false' );   // no mail server in tests
wp_install( 'GEO test blog', 'admin', 'admin@blog.example', false, '', 'test-password-123' );
update_option( 'permalink_structure', '/%postname%/' );
update_option( 'timezone_string', 'Asia/Taipei' );     // local time is 8 hours ahead of GMT: freshness must use GMT
update_option( 'blogdescription', 'Test data only' );
$result = activate_plugin( 'geo-signals/geo-signals.php' );
if ( is_wp_error( $result ) ) {
	fwrite( STDERR, $result->get_error_message() . "\n" );
	exit( 1 );
}

$add = static function ( string $title, string $content, string $status = 'publish' ): int {
	$id = wp_insert_post(
		array(
			'post_title'   => $title,
			'post_content' => $content,
			'post_status'  => $status,
			'post_author'  => 1,
		),
		true
	);
	if ( is_wp_error( $id ) ) {
		fwrite( STDERR, $id->get_error_message() . "\n" );
		exit( 1 );
	}
	return $id;
};

$cases = json_decode( file_get_contents( $argv[2] ), true )['cases'];
foreach ( $cases as $case ) {
	$add( $case['name'], $case['html'] );
}
$add(
	'Block editor post',
	"<!-- wp:heading -->\n<h2 class=\"wp-block-heading\">FAQ</h2>\n<!-- /wp:heading -->\n\n<!-- wp:paragraph -->\n" .
	"<p>依照<a href=\"https://www.cdc.gov/x\">CDC</a>資料，約 45% 的人每年 2 次。</p>\n<!-- /wp:paragraph -->\n\n" .
	"<!-- wp:quote -->\n<blockquote class=\"wp-block-quote\"><p>「先查證，再分享。」</p></blockquote>\n<!-- /wp:quote -->"
);
$old = $add( 'Old post', '<p>這篇很久沒更新，售價 990 元。</p>' );
$add( 'Draft post', '<p>草稿不應出現：<a href="https://draft.example">x</a></p>', 'draft' );
for ( $i = 1; $i <= 15; $i++ ) {
	$add( "Filler $i", "<p>第 $i 篇：<a href=\"https://source$i.example/a\">來源</a>，" . ( $i * 10 ) . '% 的讀者。</p>' );
}

// Make one post old: 400 days since its last update (set directly, as an import would).
global $wpdb;
$then = gmdate( 'Y-m-d H:i:s', time() - 400 * DAY_IN_SECONDS );
$wpdb->update( $wpdb->posts, array( 'post_modified_gmt' => $then, 'post_modified' => get_date_from_gmt( $then ) ), array( 'ID' => $old ) );
clean_post_cache( $old );

echo 'seeded ' . wp_count_posts()->publish . " published posts\n";
