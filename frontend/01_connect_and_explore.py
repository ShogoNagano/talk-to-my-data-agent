# Copyright 2024 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import asyncio
import os
import sys
import warnings
from collections import defaultdict
from typing import cast

import polars as pl
import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

sys.path.append("..")
from app_settings import (
    apply_custom_css,
    display_page_logo,
    get_database_loader_message,
    get_database_logo,
)
from datarobot_connect import DataRobotTokenManager
from helpers import state_empty, state_init

from utils.analyst_db import AnalystDB, DataSourceType
from utils.api import (
    download_catalog_datasets,
    list_catalog_datasets,
    log_memory,
    process_data_and_update_state,
)
from utils.database_helpers import Database, app_infra
from utils.logging_helper import get_logger
from utils.schema import (
    AiCatalogDataset,
    AnalystDataset,
    CleansedColumnReport,
    DataDictionary,
)

warnings.filterwarnings("ignore")

logger = get_logger("DataAnalystFrontend")


async def process_uploaded_file(file: UploadedFile) -> list[str]:
    """Process a single uploaded file and return a list of (dataset_name, dataframe) tuples

    Args:
        file: The uploaded file object
    Returns:
        list: List of (dataset_name, dataframe) tuples, or empty list if error
    """
    try:
        logger.info(f"Processing uploaded file: {file.name}")
        file_extension = os.path.splitext(file.name)[1].lower()
        results = []

        if file_extension == ".csv":
            logger.info(f"Loading CSV: {file.name}")
            log_memory()
            df = pl.read_csv(file, infer_schema_length=10000, low_memory=True)
            log_memory()
            dataset_name = os.path.splitext(file.name)[0]
            results.append(AnalystDataset(name=dataset_name, data=df))
            logger.info(
                f"Loaded CSV {dataset_name}: {len(df)} rows, {len(df.columns)} columns"
            )

        elif file_extension in [".xlsx", ".xls"]:
            # Read all sheets

            base_name = os.path.splitext(file.name)[0]
            excel_sheets = pl.read_excel(file, sheet_id=0)
            for sheet_name, data in excel_sheets.items():
                # Use sheet name as dataset name if multiple sheets, otherwise use file name
                dataset_name = f"{base_name}_{sheet_name}"
                results.append(AnalystDataset(name=dataset_name, data=data))
                logger.info(
                    f"Loaded Excel sheet {dataset_name}: {len(data)} rows, {len(data.columns)} columns"
                )
        else:
            raise ValueError(f"Unsupported file type: {file_extension}")

        analyst_db: AnalystDB = st.session_state.analyst_db
        names = []
        for result in results:
            await analyst_db.register_dataset(result, DataSourceType.FILE)
            names.append(result.name)
            del result
        del results
        return names

    except Exception as e:
        logger.error(f"Error loading {file.name}: {str(e)}", exc_info=True)
        return []


def clear_data_callback() -> None:
    """Callback function to clear all data from session state and cache"""
    # Clear session state
    state_empty()

    st.session_state.file_uploader_key += 1  # Used to clear file_uploader


# Add callback for AI Catalog dataset selection
async def catalog_download_callback() -> None:
    """Callback function for AI Catalog dataset download"""
    if (
        "selected_catalog_datasets" in st.session_state
        and st.session_state.selected_catalog_datasets
    ):
        st.session_state.data_source = DataSourceType.CATALOG

        with st.sidebar:  # Use sidebar context
            with st.spinner("Loading selected datasets..."):
                selected_ids = [
                    ds["id"] for ds in st.session_state.selected_catalog_datasets
                ]
                with st.session_state.datarobot_connect.use_user_token():
                    dataframes = await download_catalog_datasets(
                        selected_ids, st.session_state.analyst_db
                    )

                async for message in process_data_and_update_state(
                    dataframes,
                    st.session_state.analyst_db,
                    st.session_state.data_source,
                ):
                    st.toast(message)


async def load_from_database_callback() -> None:
    """Callback function for Database table download"""
    # Set flag to indicate data source is a database
    st.session_state.data_source = DataSourceType.DATABASE
    if (
        "selected_schema_tables" in st.session_state
        and st.session_state.selected_schema_tables
    ):
        with st.sidebar:
            with st.spinner("選択されたデータをロード中..."):
                dataframes = await Database.get_data(
                    *st.session_state.selected_schema_tables,
                    analyst_db=st.session_state.analyst_db,
                )

                if not dataframes:
                    st.error(f"データのロードに失敗しました {app_infra.database}")
                    return

                async for message in process_data_and_update_state(
                    dataframes,
                    st.session_state.analyst_db,
                    st.session_state.data_source,
                ):
                    st.toast(message)


async def uploaded_file_callback(uploaded_files: list[UploadedFile]) -> None:
    """Callback function for file uploads"""
    # Set flag to indicate data source is a file
    st.session_state.data_source = DataSourceType.FILE

    with st.spinner("ファイルのロードと処理中..."):
        # Process uploaded files
        for file in uploaded_files:
            if file.file_id not in st.session_state.processed_file_ids:
                logger.info("アップロードされたファイルの処理中")
                log_memory()
                dataset_results = await process_uploaded_file(file)
                logger.info("データのクレンジングと辞書の作成を開始中")
                log_memory()
                async for message in process_data_and_update_state(
                    dataset_results,
                    st.session_state.analyst_db,
                    st.session_state.data_source,
                ):
                    st.toast(message)
                logger.info("ファイルの処理が完了しました")
                log_memory()
                st.session_state.processed_file_ids.append(file.file_id)


@st.cache_data(ttl="60s", show_spinner=False)
def st_list_catalog_datasets() -> list[AiCatalogDataset]:
    return list_catalog_datasets()


@st.cache_data(ttl="60s", show_spinner=False)
def st_list_database_tables() -> list[str]:
    return Database.get_tables()


# Custom CSS
apply_custom_css()

# Initialize session state variables


async def main() -> None:
    # Sidebar for data upload and processing
    await state_init()
    logger.info("Starting App")
    with st.sidebar:
        st.title("接続")

        # Load Files expander containing file upload and AI Catalog
        with st.expander("ファイルのロード", expanded=True):
            # File upload section
            col1, col2, col3 = st.columns([1, 4, 2])
            with col1:
                st.image("csv_File_Logo.svg", width=25)
            with col2:
                st.write("**データファイルのロード**")
            uploaded_files = st.file_uploader(
                "Select 1 or multiple files",
                type=["csv", "xlsx", "xls"],
                accept_multiple_files=True,
                key=st.session_state.file_uploader_key,
            )
            if uploaded_files:
                await uploaded_file_callback(uploaded_files)

            # AI Catalog section
            st.subheader("☁️   DataRobot AIカタログ")

            # Get datasets from catalog

            with st.spinner("AIカタログからデータをロード中..."):
                with st.session_state.datarobot_connect.use_user_token():
                    datasets = [i.model_dump() for i in st_list_catalog_datasets()]

            # Create form for dataset selection
            with st.form("catalog_selection_form", border=False):
                selected_catalog_datasets = st.multiselect(
                    "データセットからAIカタログを選択する",
                    options=datasets,
                    format_func=lambda x: f"{x['name']} ({x['size']})",
                    help="You can select multiple datasets",
                    key="selected_catalog_datasets",
                )

                # Form submit button
                submit_button = st.form_submit_button(
                    "データセットのロード",
                )

                # Process form submission
                if submit_button and len(selected_catalog_datasets) > 0:
                    await catalog_download_callback()
                elif submit_button:
                    st.warning("最低限一つのデータセットを選択してください")

        # Database expander
        with st.expander("データベース", expanded=False):
            get_database_logo(app_infra)

            schema_tables = st_list_database_tables()

            # Create form for Database table selection
            with st.form("table_selection_form", border=False):
                selected_schema_tables = st.multiselect(
                    label=get_database_loader_message(app_infra),
                    options=schema_tables,
                    help="You can select multiple tables",
                    key="selected_schema_tables",
                )

                # Form submit button
                submit_button = st.form_submit_button(
                    "Load Selected Tables",
                    use_container_width=False,
                )

                if submit_button:
                    if len(selected_schema_tables) == 0:
                        st.warning("Please select at least one table")
                    else:
                        await load_from_database_callback()

        # Add Clear Data button after the Database expander
        if st.sidebar.button(
            "データの削除",
            on_click=clear_data_callback,
            type="secondary",
            use_container_width=False,
        ):
            analyst_db: AnalystDB = st.session_state.analyst_db
            await analyst_db.delete_all_tables()

    # Main content area
    display_page_logo()
    st.title("データの探索")
    if "analyst_db" not in st.session_state:
        st.warning("Could not identify user, please provide your API token")
        return

    analyst_db = cast(AnalystDB, st.session_state.analyst_db)
    dataset_names = await analyst_db.list_analyst_datasets()
    # Main content area - conditional rendering based on cleansed data
    if not dataset_names:
        st.info("Upload and process your data using the sidebar to get started")
    else:
        for ds_display_name in dataset_names:
            tab1, tab2 = st.tabs(["生データ", "データディクショナリー"])
            with tab1:
                ds_display = await analyst_db.get_dataset(ds_display_name)
                st.subheader(f"{ds_display.name}")
                cleaning_report: list[CleansedColumnReport] | None = None
                try:
                    ds_display_cleansed = await analyst_db.get_cleansed_dataset(
                        ds_display_name
                    )
                    cleaning_report = ds_display_cleansed.cleaning_report

                    # Display cleaning report in expander
                    with st.expander("クリーニングレポートを閲覧する"):
                        # Group reports by conversion type
                        conversions: defaultdict[str, list[CleansedColumnReport]] = (
                            defaultdict(list)
                        )

                        for col_report in cleaning_report:
                            if col_report.conversion_type:
                                conversions[col_report.conversion_type].append(
                                    col_report
                                )

                        # Display summary of changes
                        if conversions:
                            st.write("### 変更点の概要")
                            for conv_type, reports in conversions.items():
                                columns_count = len(reports)
                                st.write(
                                    f"**{conv_type}** ({columns_count} {'column' if columns_count == 1 else 'columns'})"
                                )
                                for report in reports:
                                    with st.container():
                                        st.markdown(f"### {report.new_column_name}")
                                        if report.original_column_name:
                                            st.write(
                                                f"Original name: `{report.original_column_name}`"
                                            )
                                        if report.original_dtype:
                                            st.write(
                                                f"Type conversion: `{report.original_dtype}` → `{report.new_dtype}`"
                                            )

                                        # Show warnings if any
                                        if report.warnings:
                                            st.write("**Warnings:**")
                                            for warning in report.warnings:
                                                st.markdown(f"- {warning}")

                                        # Show errors if any
                                        if report.errors:
                                            st.error("**Errors:**")
                                            for error in report.errors:
                                                st.markdown(f"- {error}")
                        else:
                            st.info("クリーニングで変更されたカラムはありません")

                        # Show unchanged columns
                        unchanged = [
                            r for r in cleaning_report if not r.conversion_type
                        ]
                        if unchanged:
                            st.write("### 変更されなかったカラム")
                            st.write(
                                ", ".join(f"`{r.new_column_name}`" for r in unchanged)
                            )

                except ValueError:
                    st.warning("No cleaning report available for this dataset")

                df_lock = asyncio.Lock()
                # Display dataframe with column filters

                async with df_lock:
                    df_display = ds_display.to_df()
                    # Create column filters
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        search = st.text_input(
                            "Search columns",
                            key=f"search_{ds_display.name}",
                            help="Filter columns by name",
                        )
                    with col2:
                        n_rows = int(
                            st.number_input(
                                "Rows to display",
                                min_value=1,
                                max_value=len(df_display),
                                value=min(10, len(df_display)),
                                step=1,
                                key=f"n_rows_{ds_display.name}",
                            )
                        )

                    # Filter columns based on search
                    if search:
                        cols = [
                            col
                            for col in df_display.columns
                            if search.lower() in col.lower()
                        ]
                    else:
                        cols = df_display.columns

                    # Display filtered dataframe
                    st.dataframe(
                        df_display[cols].head(n_rows), use_container_width=True
                    )

                    # Download button
                    col1, col2, col3 = st.columns([1, 3, 1])
                    with col1:
                        csv = df_display.write_csv()
                        st.download_button(
                            label="Download Data",
                            data=csv,
                            file_name=f"{ds_display.name}_cleansed.csv",
                            mime="text/csv",
                            key=f"download_{ds_display.name}",
                        )
                    with col3:
                        if st.button(
                            "Delete Dataset",
                            key=f"delete_{ds_display.name}",
                            use_container_width=True,
                        ):
                            await analyst_db.delete_table(ds_display.name)
                            st.rerun()

            with tab2:
                try:
                    dictionary = await analyst_db.get_data_dictionary(ds_display.name)
                    if dictionary is None:
                        st.error("No data dictionary found for this dataset.")
                        return

                    # Convert dictionary to DataFrame
                    dict_df = dictionary.to_application_df()
                    logger.info(
                        f"Created DataFrame for {dictionary.name} with shape {dict_df.shape}"
                    )

                    # Make dictionary editable
                    edited_df = pl.DataFrame(
                        st.data_editor(
                            dict_df,
                            use_container_width=True,
                            num_rows="dynamic",
                            key=f"dict_editor_{dictionary.name}",
                        )
                    )

                    col1, col2, col3 = st.columns([2, 3, 1])

                    with col3:
                        if st.button(
                            label="変更を保存する",
                            key=f"dict_save_{dictionary.name}",
                            use_container_width=True,
                        ):
                            await analyst_db.delete_dictionary(dictionary.name)
                            await analyst_db.register_data_dictionary(
                                DataDictionary.from_application_df(
                                    edited_df, ds_display.name
                                ),
                            )

                    with col1:
                        # Download button for dictionary
                        csv = edited_df.write_csv()
                        st.download_button(
                            label="データディクショナリーをダウンロードする",
                            data=csv,
                            file_name=f"{dictionary.name}_dictionary.csv",
                            mime="text/csv",
                            key=f"download_dict_{dictionary.name}",
                        )

                except Exception as e:
                    logger.error(
                        f"Error processing dictionary for {ds_display.name}: {str(e)}",
                        exc_info=True,
                    )
                    st.error(
                        f"Error displaying dictionary for {ds_display.name}: {str(e)}"
                    )

                st.markdown("---")


if __name__ == "__main__":
    if "datarobot_connect" not in st.session_state:
        datarobot_connect = DataRobotTokenManager()
        st.session_state.datarobot_connect = datarobot_connect
    asyncio.run(main())
else:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
