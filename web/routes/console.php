<?php

use Illuminate\Foundation\Inspiring;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Schedule;

Artisan::command('inspire', function () {
    $this->comment(Inspiring::quote());
})->purpose('Display an inspiring quote');

// Telescope records every request/query/job by design (§System health, the AI-usage
// screen, and this both feed off real traffic) — without pruning, telescope_entries
// grows forever. 48h is enough to debug something found today or yesterday.
Schedule::command('telescope:prune', ['--hours' => 48])->daily();
