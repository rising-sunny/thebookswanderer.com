    # --- Search Console on demand (inserted by deploy/seo-query/seo_query_install.py) ---
    async def _seo_call(path, payload):
        try:
            async with httpx2.AsyncClient(timeout=60, follow_redirects=False) as client:
                response = await client.post(
                    "http://127.0.0.1:8881" + path, json=payload,
                    headers={"Authorization": "Bearer " + admin_key.strip()},
                )
        except httpx2.HTTPError:
            raise ToolError("Search Console query service unavailable") from None
        try:
            data = response.json()
        except ValueError:
            raise ToolError("Invalid Search Console service response") from None
        if response.status_code != 200:
            detail = data.get("detail") if isinstance(data, dict) else None
            raise ToolError(str(detail or f"Search Console service HTTP {response.status_code}")[:400])
        return data

    @server.tool(annotations=SUPPLIER)
    async def tbw_seo_query(
        start_date: Annotated[date | None, Field(description="YYYY-MM-DD; default 28 days before end_date")] = None,
        end_date: Annotated[date | None, Field(description="YYYY-MM-DD; default 3 days ago")] = None,
        dimensions: Annotated[
            list[Literal["page", "query", "date", "country", "device"]],
            Field(min_length=1, max_length=3),
        ] = ["page"],
        page: Annotated[str | None, Field(max_length=500, description="Full URL for an exact page, or text a page URL contains")] = None,
        query: Annotated[str | None, Field(max_length=500, description="Text the search query contains")] = None,
        country: Annotated[str | None, Field(pattern=r"^[A-Za-z]{3}$", description="3-letter code, e.g. usa, chl")] = None,
        row_limit: Annotated[int, Field(ge=1, le=250)] = 50,
    ) -> dict:
        """Query Search Console performance for The Books Wanderer on demand:
        clicks, impressions, CTR and position by page, query, date, country or
        device for any range in the last 16 months, with optional page/query
        filters. Includes fresh data. Read-only; does not edit the website.
        """
        payload = {"dimensions": dimensions, "row_limit": row_limit}
        for name, value in (("start_date", start_date), ("end_date", end_date)):
            if value is not None:
                payload[name] = value.isoformat()
        for name, value in (("page", page), ("query", query), ("country", country)):
            if value is not None:
                payload[name] = value
        return await _seo_call("/query", payload)

    @server.tool(annotations=SUPPLIER)
    async def tbw_seo_inspect_url(
        url: Annotated[str, Field(pattern=r"^https://thebookswanderer\.com/\S{0,2000}$")],
    ) -> dict:
        """Inspect one thebookswanderer.com URL in Search Console: whether it is
        indexed, coverage state, last crawl, canonical chosen by Google, sitemaps
        and rich results. Read-only; requesting indexing must be done by hand in
        Search Console. Limited to 60 inspections per hour.
        """
        return await _seo_call("/inspect", {"url": url})
    # --- end Search Console on demand ---

