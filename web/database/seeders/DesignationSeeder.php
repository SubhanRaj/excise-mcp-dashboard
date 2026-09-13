<?php

namespace Database\Seeders;

use App\Models\Designation;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

/**
 * The excise-specific rank ladder, reused from excise-budget-tracker and
 * UP-excise-mailer's own DesignationSeeders rather than inventing new titles —
 * mapped here onto this app's four privileges (web/plan/webui.md §6).
 */
class DesignationSeeder extends Seeder
{
    public function run(): void
    {
        $rows = [
            ['name' => 'Excise Commissioner', 'default_privileges' => ['*']],
            ['name' => 'Additional Excise Commissioner', 'default_privileges' => ['*']],
            ['name' => 'System Engineer', 'default_privileges' => ['*']],
            ['name' => 'Deputy Excise Commissioner', 'default_privileges' => ['kb.manage']],
            ['name' => 'District Excise Officer', 'default_privileges' => ['kb.manage']],
            ['name' => 'Assistant Excise Commissioner', 'default_privileges' => []],
            ['name' => 'Officer', 'default_privileges' => []],
        ];

        foreach ($rows as $i => $row) {
            Designation::updateOrCreate(
                ['slug' => Str::slug($row['name'])],
                [
                    'name' => $row['name'],
                    'default_privileges' => $row['default_privileges'],
                    'sort_order' => $i,
                ]
            );
        }
    }
}
