"""Flask 应用工厂。"""
from __future__ import annotations

import os

from flask import Flask, render_template, request

import config as C
from .extensions import db


def create_app(database_url: str | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        instance_path=str(C.INSTANCE),
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url or C.DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JSON_AS_ASCII"] = False
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "recsys-course-2026")

    db.init_app(app)

    from .api import api
    from .admin import admin
    app.register_blueprint(api)
    app.register_blueprint(admin)

    # ------------------------------------------------------------ 页面路由
    @app.get("/")
    def index():
        ds = request.args.get("dataset", C.PRIMARY_DATASET)
        return render_template("index.html", dataset=ds, page="home")

    @app.get("/item/<int:item_id>")
    def item_page(item_id: int):
        ds = request.args.get("dataset", C.PRIMARY_DATASET)
        return render_template("detail.html", dataset=ds, item_id=item_id,
                               page="item")

    @app.get("/recommend")
    def recommend_page():
        ds = request.args.get("dataset", C.PRIMARY_DATASET)
        return render_template("recommend.html", dataset=ds, page="recommend")

    @app.get("/dashboard")
    def dashboard_page():
        ds = request.args.get("dataset", C.PRIMARY_DATASET)
        return render_template("dashboard.html", dataset=ds, page="dashboard")

    @app.get("/about")
    def about_page():
        return render_template("about.html", dataset=C.PRIMARY_DATASET, page="about")

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html", page=""), 404

    return app
