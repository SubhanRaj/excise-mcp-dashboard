<?php

namespace Tests\Unit;

use App\Support\Money;
use PHPUnit\Framework\TestCase;

class MoneyTest extends TestCase
{
    public function test_rupees_unit_groups_digits_the_indian_way(): void
    {
        $this->assertSame('₹1,23,45,678', Money::format(12345678, 'rupees'));
        $this->assertSame('₹1,000', Money::format(1000, 'rupees'));
        $this->assertSame('₹999', Money::format(999, 'rupees'));
    }

    public function test_lakh_and_crore_units_divide_and_suffix(): void
    {
        $this->assertSame('₹1.23 L', Money::format(123_000, 'lakh'));
        $this->assertSame('₹1.23 Cr', Money::format(12_300_000, 'crore'));
        $this->assertSame('₹1.00 K', Money::format(1_000, 'thousand'));
    }

    public function test_negative_amount_keeps_the_sign(): void
    {
        $this->assertSame('₹-1,000', Money::format(-1000, 'rupees'));
    }
}
