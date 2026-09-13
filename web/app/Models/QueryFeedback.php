<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Concerns\HasUlids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

#[Fillable(['query_id', 'user_id', 'thumbs_up', 'note'])]
class QueryFeedback extends Model
{
    use HasUlids;

    protected function casts(): array
    {
        return [
            'thumbs_up' => 'boolean',
        ];
    }

    // Named askQuery(), not query() — Query::class is this model's parent, but
    // Eloquent's base Model already defines a *static* query() builder method,
    // and overriding it with an instance method is a fatal error at class load.
    public function askQuery(): BelongsTo
    {
        return $this->belongsTo(Query::class);
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }
}
