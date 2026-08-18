"""Командная строка traffic-engine.

Пока одна команда — ``profile``. Она отвечает на вопрос, который надо
задать раньше всех остальных: что вообще лежит в скачанных файлах и
можно ли на этом что-то строить.
"""

from __future__ import annotations

from pathlib import Path

import typer

from traffic_engine.ingestion import load_station_5min
from traffic_engine.ingestion.meta import load_station_meta
from traffic_engine.ingestion.station_5min import load_station_5min_dir
from traffic_engine.quality import profile_station_5min
from traffic_engine.quality.profile import unusable_stations

app = typer.Typer(
    add_completion=False,
    help="Время поездки как распределение, а не как одно число.",
)


@app.command()
def profile(
    path: Path = typer.Argument(..., help="файл .txt.gz или каталог с суточными файлами"),
    show_worst: int = typer.Option(10, help="сколько худших станций показать"),
    keep_lanes: bool = typer.Option(False, help="читать колонки по отдельным полосам"),
) -> None:
    """Отчёт о структуре и качестве выгрузки Station 5-Minute."""
    if path.is_dir():
        df = load_station_5min_dir(path, keep_lanes=keep_lanes)
    else:
        df = load_station_5min(path, keep_lanes=keep_lanes)

    report = profile_station_5min(df)
    typer.echo(report.to_text())

    if report.per_station is not None and show_worst:
        typer.echo("")
        typer.echo(f"ХУДШИЕ {show_worst} СТАНЦИЙ ПО НАБЛЮДАЕМОСТИ")
        typer.echo("-" * 60)
        typer.echo(report.per_station.head(show_worst).to_string())

    bad = unusable_stations(report)
    if bad:
        typer.echo("")
        typer.echo(f"К выбросу ({len(bad)} шт.): {bad[:30]}{' …' if len(bad) > 30 else ''}")


@app.command()
def meta(
    path: Path = typer.Argument(..., help="файл метаданных станций"),
    freeway: int = typer.Option(405, help="номер автомагистрали"),
    direction: str = typer.Option("S", help="направление N/S/E/W"),
) -> None:
    """Показать станции одной автомагистрали в порядке движения."""
    m = load_station_meta(path)
    sel = m[(m["freeway"] == freeway) & (m["direction"] == direction)]
    if "lane_type" in sel.columns:
        sel = sel[sel["lane_type"] == "ML"]
    ascending = direction in ("N", "E")
    sel = sel.sort_values("abs_pm", ascending=ascending)

    cols = [
        c
        for c in ("station", "abs_pm", "latitude", "longitude", "lanes", "name")
        if c in sel.columns
    ]
    typer.echo(f"станций основного хода на I-{freeway} {direction}: {len(sel)}")
    if len(sel):
        typer.echo(f"постмили: {sel['abs_pm'].min():.2f} … {sel['abs_pm'].max():.2f}")
    typer.echo(sel[cols].to_string(index=False))


if __name__ == "__main__":  # pragma: no cover
    app()
