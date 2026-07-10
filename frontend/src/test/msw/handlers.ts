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

export const handlers = [
  http.get(`${BASE}/meta/building-types`, () =>
    HttpResponse.json(buildingTypes)
  ),
  http.get(`${BASE}/meta/segments`, () =>
    HttpResponse.json(residentialSegments)
  ),
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
]
