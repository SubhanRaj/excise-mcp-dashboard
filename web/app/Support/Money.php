<?php

namespace App\Support;

/**
 * Rupees rendered in a chosen unit (CLAUDE.md's Formatting convention).
 * upexcise-stats-dashboard has no reusable formatter to port — every view
 * there repeats its own crore/lakh division inline — so this centralizes it
 * instead of repeating that per view here too.
 */
final class Money
{
    public const UNITS = [
        'rupees' => 1,
        'thousand' => 1_000,
        'lakh' => 100_000,
        'crore' => 10_000_000,
    ];

    public static function format(int|float $amount, string $unit = 'rupees'): string
    {
        $divisor = self::UNITS[$unit] ?? 1;
        $value = $amount / $divisor;

        if ($unit === 'rupees') {
            return '₹'.self::groupIndian($value);
        }

        $suffix = match ($unit) {
            'thousand' => 'K',
            'lakh' => 'L',
            'crore' => 'Cr',
            default => '',
        };

        return '₹'.number_format($value, 2).' '.$suffix;
    }

    /**
     * "1,23,456" — the last three digits, then groups of two, the digit
     * grouping en-IN locale strings use and Cleave.js's numeralThousandsGroupStyle:
     * 'lakh' already applies to the currency-input component below.
     */
    private static function groupIndian(int|float $value): string
    {
        $intPart = number_format((float) $value, 0, '.', '');
        $negative = str_starts_with($intPart, '-');
        $intPart = ltrim($intPart, '-');

        $last3 = substr($intPart, -3);
        $rest = substr($intPart, 0, -3);
        if ($rest !== '') {
            $rest = preg_replace('/\B(?=(\d{2})+(?!\d))/', ',', $rest);
            $last3 = $rest.','.$last3;
        }

        return ($negative ? '-' : '').$last3;
    }
}
