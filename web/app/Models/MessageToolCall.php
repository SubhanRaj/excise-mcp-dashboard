<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Concerns\HasUlids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\MorphOne;
use Illuminate\Database\Eloquent\SoftDeletes;

#[Fillable(['message_id', 'tool_name', 'arguments', 'result_summary'])]
class MessageToolCall extends Model
{
    use HasUlids, SoftDeletes;

    protected function casts(): array
    {
        return [
            'arguments' => 'array',
            'result_summary' => 'array',
        ];
    }

    public function message(): BelongsTo
    {
        return $this->belongsTo(Message::class);
    }

    public function chartArtifact(): MorphOne
    {
        return $this->morphOne(ChartArtifact::class, 'owner');
    }
}
