<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Concerns\HasUlids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\MorphOne;
use Illuminate\Database\Eloquent\SoftDeletes;

#[Fillable([
    'user_id', 'request_id', 'prompt', 'sql', 'engine', 'model', 'tables_used',
    'row_count', 'timings', 'status', 'current_stage', 'rows_preview', 'summary', 'error_message',
])]
class Query extends Model
{
    use HasUlids, SoftDeletes;

    protected function casts(): array
    {
        return [
            'tables_used' => 'array',
            'timings' => 'array',
            'rows_preview' => 'array',
        ];
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function chartArtifact(): MorphOne
    {
        return $this->morphOne(ChartArtifact::class, 'owner');
    }

    public function isTerminal(): bool
    {
        return in_array($this->status, ['complete', 'failed'], true);
    }
}
