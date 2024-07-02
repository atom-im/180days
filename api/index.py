from flask import Flask, request, render_template, redirect, url_for, flash, send_from_directory
import pdfplumber
import pandas as pd
from datetime import datetime
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp'
app.secret_key = 'supersecretkey'  # Required for flash messages

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

def clean_cell(cell):
    """Clean individual cell data by removing unwanted characters."""
    if isinstance(cell, str):
        return cell.strip().replace('\n', '').replace('\r', '')
    return cell

def extract_tables_from_pdf(pdf_path):
    all_rows = []
    columns = None
    text_found = False

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages):
            # Check if the required text is in the page
            if "出入境记录查询结果" in page.extract_text():
                text_found = True

            tables = page.extract_tables()
            for table in tables:
                if page_number == 0:
                    columns = [clean_cell(col) for col in table[0]]  # Clean header
                    rows = table[1:]
                else:
                    rows = table

                cleaned_rows = [[clean_cell(cell) for cell in row] for row in rows]
                all_rows.extend(cleaned_rows)

    if not text_found:
        raise ValueError("请重新上传正确的出入境记录查询结果（电子文件）。参考下方使用说明。")

    if columns is None:
        raise ValueError("No table header found in the first page of the PDF.")

    combined_df = pd.DataFrame(all_rows, columns=columns)
    return combined_df

def calculate_days_in_china(df):
    df['出入境日期'] = pd.to_datetime(df['出入境日期']).dt.date
    current_date = datetime.now().date()
    results = []

    first_record = df.iloc[0]
    if first_record['出境/入境'] == '出境':
        for i in range(1, len(df), 2):
            if i+1 <= len(df):
                entry_date = df.iloc[i]['出入境日期']
                exit_date = df.iloc[i-1]['出入境日期']
                days_in_china = (exit_date - entry_date).days
                results.append([entry_date, exit_date, days_in_china])
    else:
        entry_date = first_record['出入境日期']
        days_in_china = (current_date - entry_date).days
        results.append([entry_date, current_date, days_in_china])

        for i in range(2, len(df), 2):
            if i < len(df):
                entry_date = df.iloc[i]['出入境日期']
                exit_date = df.iloc[i-1]['出入境日期']
                days_in_china = (exit_date - entry_date).days
                results.append([entry_date, exit_date, days_in_china])

    results_df = pd.DataFrame(results, columns=['Entry Date', 'Exit Date', 'Days in China'])
    results_df = results_df.sort_values(by='Days in China', ascending=False).reset_index(drop=True)
    return results_df

def highlight_days_in_china(days):
    """Highlight days in China if greater than 180."""
    if days > 180:
        return f'<span style="color: red;">{days}</span>'
    return str(days)

def results_to_html(results_df):
    """Convert results DataFrame to HTML with highlighted days."""
    html = '<table border="1">'
    html += '<tr><th>入境日期</th><th>出境日期</th><th>居住天数</th></tr>'
    for _, row in results_df.iterrows():
        entry_date = row['Entry Date']
        exit_date = row['Exit Date']
        days_in_china = highlight_days_in_china(row['Days in China'])
        html += f'<tr><td>{entry_date}</td><td>{exit_date}</td><td>{days_in_china}</td></tr>'
    html += '</table>'
    return html

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)
            try:
                df = extract_tables_from_pdf(file_path)
                results_df = calculate_days_in_china(df)
                results_html = results_to_html(results_df)
            except ValueError as e:
                flash(str(e))
                return redirect(request.url)
            finally:
                # Remove the uploaded file after processing
                os.remove(file_path)
            return render_template('results.html', results=results_html)
    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=False)
