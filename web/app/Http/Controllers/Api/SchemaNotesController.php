<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\SchemaNote;
use Illuminate\Http\JsonResponse;

class SchemaNotesController extends Controller
{
    /**
     * Every admin-edited schema note, flat — schema_card.py's fetch_note_overrides()
     * splits table-level notes (column_name === '') from column-level ones itself.
     */
    public function index(): JsonResponse
    {
        return response()->json(
            SchemaNote::query()->select('table_name', 'column_name', 'note')->get()
        );
    }
}
