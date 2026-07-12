import { http, HttpResponse } from "msw"

const BASE = "/api"

export const buildingTypes = [
  { id: 1, code: "residential", name: "Жилые здания", sort_order: 1 },
  { id: 2, code: "office", name: "Офисные здания / ТРЦ", sort_order: 2 },
]

export const residentialSegments = [
  {
    id: 11,
    building_type_id: 1,
    group_id: null,
    name: "Бизнес",
    sort_order: 4,
  },
  {
    id: 12,
    building_type_id: 1,
    group_id: null,
    name: "Эконом",
    sort_order: 6,
  },
]

export const dashboardFixture = {
  summary: {
    positions_active: 412,
    releases_published: 18,
    drafts_open: 3,
    vendors_total: 248,
    vendors_with_agreement: 142,
    merge_candidate_pairs: 6,
  },
  drafts: [
    {
      release_id: 1,
      building_type_name: "Жилой дом",
      label: "Бизнес v4",
      last_touched_at: "2026-07-09T10:00:00Z",
      last_touched_by: "ivanov",
      is_stale: false,
    },
    {
      release_id: 3,
      building_type_name: "Соцобъект",
      label: "Базовый v2",
      last_touched_at: "2026-06-25T10:00:00Z",
      last_touched_by: "petrov",
      is_stale: true,
    },
  ],
}

export const vendorFixture = {
  id: 5,
  name: "System Air",
  kind: "manufacturer",
  note: null as string | null,
  starred: true,
  represents: null as { id: number; name: string } | null,
  represented_count: 0,
  aliases: [
    { id: 1, alias: "System Air" },
    { id: 2, alias: "SystemAir" },
  ],
}

export const whereAllowedFixture = {
  standards: [
    {
      building_type_id: 1,
      building_type_name: "Жилой дом",
      position_count: 1,
      segment_count: 2,
      positions: [
        {
          position_id: 100,
          position_name: "Радиаторы отопления",
          chips: [
            {
              segment_id: 11,
              segment_name: "Делюкс",
              state: "allowed",
              release_label: null,
            },
            {
              segment_id: 14,
              segment_name: "Бизнес",
              state: "excluded",
              release_label: "ред. 25.03.2026",
            },
          ],
        },
      ],
    },
  ],
}

export const handlers = [
  http.get(`${BASE}/meta/building-types`, () =>
    HttpResponse.json(buildingTypes)
  ),
  http.get(`${BASE}/meta/segments`, () =>
    HttpResponse.json(residentialSegments)
  ),
  http.get(`${BASE}/dashboard`, () => HttpResponse.json(dashboardFixture)),
  http.get(`${BASE}/listings/matrix`, () =>
    HttpResponse.json({
      columns: [
        { group: null, segments: [{ id: 11, name: "Бизнес", sort_order: 4 }] },
        { group: null, segments: [{ id: 12, name: "Эконом", sort_order: 6 }] },
      ],
      items: [
        {
          position_id: 100,
          position_name: "Насосы",
          category_path: "Оборудование / ОВиК",
          cells: [
            {
              segment_id: 11,
              vendors: [
                {
                  vendor_id: 5,
                  name: "Grundfos",
                  starred: true,
                  ujin_integration: false,
                  note: null,
                },
              ],
              spec_text: null,
              note: null,
            },
            { segment_id: 12, vendors: [], spec_text: "Россия", note: null },
          ],
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    })
  ),
  http.get(`${BASE}/vendors/:vendorId`, () => HttpResponse.json(vendorFixture)),
  http.get(`${BASE}/vendors/:vendorId/where-allowed`, () =>
    HttpResponse.json(whereAllowedFixture)
  ),
]
