<?php
/**
 * Parity test: the WordPress plugin's rules must give exactly the numbers in tests/fixtures/signals_cases.json,
 * the same file the Python tests use. Run: php tests/php/test_signals.php
 */

require __DIR__ . '/../../wordpress-plugin/geo-signals/includes/signals.php';

$fixture = json_decode( file_get_contents( __DIR__ . '/../fixtures/signals_cases.json' ), true );
$failed  = 0;
foreach ( $fixture['cases'] as $case ) {
	$got = geo_signals_compute( $case['html'], $case['own_domain'] );
	if ( $got !== $case['expected'] ) {
		$failed++;
		echo "FAIL {$case['name']}\n  expected " . json_encode( $case['expected'] ) . "\n  got      " . json_encode( $got ) . "\n";
	} else {
		echo "ok   {$case['name']}\n";
	}
}

// Freshness: whole days, rounded down, from a UTC timestamp.
$now = strtotime( '2026-10-09 12:00:00 UTC' );
$checks = array(
	array( geo_signals_days_since( '2026-10-08 12:00:01', $now ), 0 ),
	array( geo_signals_days_since( '2026-10-08 12:00:00', $now ), 1 ),
	array( geo_signals_days_since( '2026-04-12 00:00:00', $now ), 180 ),
);
foreach ( $checks as $i => list( $got, $want ) ) {
	if ( $got !== $want ) {
		$failed++;
		echo "FAIL days_since #$i: expected $want, got $got\n";
	}
}
echo $failed ? "$failed failed\n" : "all passed\n";
exit( $failed ? 1 : 0 );
