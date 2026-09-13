<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->string('username')->unique()->after('name');
            $table->string('mobile', 10)->nullable()->after('email');
            $table->string('role')->default('Analyst')->after('mobile');
            $table->string('post', 100)->nullable()->after('role');
            $table->json('privileges')->nullable()->after('post');
            $table->json('ui_prefs')->nullable()->after('privileges');
            $table->softDeletes();

            // Admin-created accounts are passwordless until they accept the signed invite.
            $table->string('password')->nullable()->change();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->dropColumn(['username', 'mobile', 'role', 'post', 'privileges', 'ui_prefs', 'deleted_at']);
        });
    }
};
