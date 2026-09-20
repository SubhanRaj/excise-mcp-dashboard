<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Concerns\HasUlids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\MorphTo;
use Illuminate\Database\Eloquent\SoftDeletes;

#[Fillable(['owner_type', 'owner_id', 'spec', 'png_path', 'svg_path', 'pdf_path'])]
class ChartArtifact extends Model
{
    use HasUlids, SoftDeletes;

    protected function casts(): array
    {
        return [
            'spec' => 'array',
        ];
    }

    public function owner(): MorphTo
    {
        return $this->morphTo();
    }

    /**
     * A plain Plotly figure ({data, layout}) regardless of which flow stored
     * this artifact: RunExciseQuery stores the parsed figure directly, while
     * ChatController stores {plotly_json, files} — the whole tool result
     * dict, with the figure still JSON-encoded inside it.
     */
    public function plotlyFigure(): ?array
    {
        if (isset($this->spec['plotly_json'])) {
            return json_decode($this->spec['plotly_json'], true);
        }

        return $this->spec;
    }

    /**
     * The chart's owning user, resolved through whichever flow produced it —
     * a Query has one directly, a MessageToolCall only through its message's
     * conversation. Used to authorize a chart export request. Neither
     * Query::$user_id nor Conversation::$user_id is cast to int, so this
     * casts explicitly rather than leaving a caller to compare a DB string
     * against auth()->id()'s int and silently fail every ===.
     */
    public function ownerUserId(): ?int
    {
        $userId = match ($this->owner_type) {
            Query::class => $this->owner?->user_id,
            MessageToolCall::class => $this->owner?->message?->conversation?->user_id,
            default => null,
        };

        return $userId !== null ? (int) $userId : null;
    }
}
