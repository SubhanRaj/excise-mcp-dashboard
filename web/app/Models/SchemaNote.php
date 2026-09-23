<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;

/**
 * An admin-edited note on one analytics.* table or column — read by the data-dictionary
 * screen (SchemaNotesIndex) and, over GET /api/schema-notes, by the orchestrator's own
 * schema_card.py, which folds these into the prompt handed to the SQL-planning model
 * (CLAUDE.md §Data dictionary). An empty column_name means the note is about the table
 * itself, not one column.
 */
#[Fillable(['table_name', 'column_name', 'note'])]
class SchemaNote extends Model {}
