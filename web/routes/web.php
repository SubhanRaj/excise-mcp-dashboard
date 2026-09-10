<?php

use Illuminate\Support\Facades\Route;

// The only route the perimeter leaves open (ROADMAP Milestone 6). Every other
// route lands behind auth once the auth port arrives.
Route::get('/health', fn () => response()->json([
    'app' => config('app.name'),
    'status' => 'ok',
]));
