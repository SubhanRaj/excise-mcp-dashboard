<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('google_connections', function (Blueprint $table) {
            $table->ulid('id')->primary();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->string('google_sub');
            $table->string('email');
            $table->json('scopes')->nullable();
            $table->text('refresh_token');
            $table->timestamp('revoked_at')->nullable();
            $table->timestamps();
            $table->softDeletes();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('google_connections');
    }
};
