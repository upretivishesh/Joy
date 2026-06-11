from io import BytesIO

import pandas as pd


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Joy Results") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return output.getvalue()
