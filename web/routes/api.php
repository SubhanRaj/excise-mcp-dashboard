<?php

use App\Http\Controllers\Api\SchemaNotesController;
use Illuminate\Support\Facades\Route;

// The one route the orchestrator calls into web/ rather than the other way around —
// gated by the same shared bearer token web/'s own OrchestratorClient sends outbound
// (VerifyOrchestratorToken), not Laravel's session auth.
Route::middleware('orchestrator.token')->get('/schema-notes', [SchemaNotesController::class, 'index']);
