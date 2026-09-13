<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Concerns\HasUlids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;

#[Fillable(['conversation_id', 'role', 'content', 'model'])]
class Message extends Model
{
    use HasUlids, SoftDeletes;

    public function conversation(): BelongsTo
    {
        return $this->belongsTo(Conversation::class);
    }

    public function toolCalls(): HasMany
    {
        return $this->hasMany(MessageToolCall::class);
    }
}
