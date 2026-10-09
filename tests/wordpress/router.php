<?php
/**
 * Router for PHP's built-in server: real files and folders are served as usual; every other path
 * (pretty permalinks, /wp-json/...) goes to WordPress's index.php, as Apache's rewrite rules would do.
 */
$path = parse_url( $_SERVER['REQUEST_URI'], PHP_URL_PATH );
if ( '/' !== $path && file_exists( $_SERVER['DOCUMENT_ROOT'] . $path ) ) {
	return false;
}
$_SERVER['SCRIPT_NAME'] = '/index.php';
require $_SERVER['DOCUMENT_ROOT'] . '/index.php';
