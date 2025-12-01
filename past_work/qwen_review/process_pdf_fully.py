# process_pdf_fully.py (Consolidated with Pre-scan Logic - Batch Processing Version with Resume Support)
import base64
import io
import os
import re
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from pdf2image import convert_from_path
    from PIL import Image
    import openai
    import pdfplumber
except ImportError as e:
    print(f"Error: Missing required libraries: {e}. Please run 'pip install -r requirements.txt' to install them.")
    exit()



# --- Module 1: PDF to Image Converter ---
class PDFToImageConverter:
    """Responsible for converting a PDF file into a series of images."""
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path

    def convert(self) -> List[Dict[str, Any]]:
        """Converts all pages of a PDF to Base64 encoded PNG images."""
        print(f"Starting conversion of all pages of the PDF to images...")
        try:
            # The last_page parameter is removed to convert all pages
            images = convert_from_path(self.pdf_path)
        except Exception as e:
            raise RuntimeError(
                "Failed to convert PDF to images. Please ensure Poppler is correctly installed on your system and its bin directory is in the system's PATH environment variable."
                f"Original error: {e}"
            )

        results = []
        for i, image in enumerate(images):
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()
            base64_string = base64.b64encode(image_bytes).decode('utf-8')
            results.append({
                "page_number": i + 1,
                "image_base64": base64_string
            })
        print(f"Successfully converted {len(results)} pages.")
        return results

# --- Module 2: Interaction with vLLM Local Model ---
def extract_text_from_image_with_llm(image_base64: str, page_number: int) -> str:
    """调用vLLM部署的本地qwen-vl-max模型来提取图像中的文本"""
    # vLLM 服务配置（确保 vLLM 服务已启动）
    base_url = "http://10.176.59.101:8001/v1"
    model_name = "qwen-vl-max"
    api_key = "EMPTY"  # vLLM 不需要实际的 API 密钥

    try:
        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional document analysis assistant. Your task is to extract specific text from a document page image. Follow these rules with extreme precision:\n1. Your ONLY output should be the main body text, headings, and mathematical formulas.\n2. You MUST COMPLETELY IGNORE anything that appears to be a table, figure, chart, or diagram. Do not extract any text from them, and do not mention them or use any placeholders. Treat them as if they do not exist.\n3. Accurately convert all mathematical formulas to LaTeX or Markdown format.\n4. Preserve all headings (e.g., 'Abstract', 'Introduction', 'References', 'Appendix') and ensure each one starts on a new line.\n5. Do not include headers, footers, or page numbers.\n6. Output only the extracted text directly, with no extra explanations or comments."
                },
                {
                    "role": "user",
                    "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}] 
                }
            ]
        )
        extracted_text = response.choices[0].message.content
        return extracted_text or ""
    except Exception as e:
        error_message = f"[vLLM API call failed for page {page_number}: {e}]"
        print(f"    {error_message}")
        return error_message

# --- Module 3: Main Orchestration (Concurrent Version) ---
def process_pdf_and_extract_text(pdf_path: str) -> str:
    """The complete processing flow: convert all pages -> concurrently call LLM to extract and combine text."""
    if not Path(pdf_path).is_file():
        return f"Error: File not found at {pdf_path}"

    # Step 1: Convert all pages of the PDF to images
    converter = PDFToImageConverter(pdf_path)
    image_data_list = converter.convert()
    
    extracted_texts = {}
    print("Starting parallel processing of all pages...")

    # Step 2: Use a thread pool to call the API in parallel for all pages
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_page = {executor.submit(extract_text_from_image_with_llm, item['image_base64'], item['page_number']): item['page_number'] for item in image_data_list}

        for future in as_completed(future_to_page):
            page_num = future_to_page[future]
            try:
                text = future.result()
                extracted_texts[page_num] = text
                print(f"  Page {page_num} processed.")
            except Exception as exc:
                error_text = f"[A critical error occurred while generating page {page_num}: {exc}]"
                extracted_texts[page_num] = error_text
                print(f"  {error_text}")

    print("All pages processed. Assembling results in order...")

    # Step 3: Concatenate the final text in page order
    final_text_parts = []
    for i in range(1, len(image_data_list) + 1):
        text = extracted_texts.get(i, f"[No content for page {i}]")
        final_text_parts.append(f"--- Page {i} ---\n{text}")
    
    full_text = "\n\n".join(final_text_parts)
    
    return full_text

# --- Resume Support Functions ---
class ProcessingProgress:
    """管理PDF处理进度的类"""
    
    def __init__(self, output_folder: str):
        self.output_folder = Path(output_folder)
        self.progress_dir = self.output_folder / ".processing"
        self.progress_dir.mkdir(parents=True, exist_ok=True)
        self.progress_file = self.progress_dir / "progress.json"
        self.state_file = self.progress_dir / "state.json"
        self.progress = self.load_progress()
    
    def load_progress(self) -> Dict[str, Any]:
        """加载处理进度"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    progress = json.load(f)
                # 将列表转换回集合
                if 'processed_files' in progress:
                    progress['processed_files'] = set(progress['processed_files'])
                print(f"📂 发现断点文件，已处理 {len(progress.get('processed_files', []))} 个PDF文件")
                return progress
            except Exception as e:
                print(f"⚠️ 无法加载断点文件: {e}")
        
        return {
            'processed_files': set(),
            'failed_files': [],
            'success_count': 0,
            'failed_count': 0,
            'start_time': datetime.now().isoformat(),
            'last_update': None,
            'total_files': 0
        }
    
    def save_progress(self):
        """保存处理进度"""
        self.progress['last_update'] = datetime.now().isoformat()
        try:
            # 将集合转换为列表以便JSON序列化
            progress_to_save = self.progress.copy()
            if 'processed_files' in progress_to_save:
                progress_to_save['processed_files'] = list(progress_to_save['processed_files'])
            
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress_to_save, f, ensure_ascii=False, indent=2)
            
            # 保存可读的状态文件
            readable_state = {
                'processed_files_count': len(self.progress['processed_files']),
                'success_count': self.progress['success_count'],
                'failed_count': self.progress['failed_count'],
                'total_files': self.progress['total_files'],
                'progress_percentage': (
                    len(self.progress['processed_files']) / max(1, self.progress['total_files'])
                ) * 100,
                'start_time': self.progress['start_time'],
                'last_update': self.progress['last_update']
            }
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(readable_state, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"⚠️ 保存进度失败: {e}")
    
    def is_processed(self, pdf_id: str) -> bool:
        """检查PDF是否已处理"""
        return pdf_id in self.progress['processed_files']
    
    def mark_processed(self, pdf_id: str, success: bool = True):
        """标记PDF为已处理"""
        self.progress['processed_files'].add(pdf_id)
        if success:
            self.progress['success_count'] += 1
        else:
            self.progress['failed_count'] += 1
        self.save_progress()
    
    def mark_failed(self, pdf_id: str, error: str):
        """记录失败的PDF"""
        self.progress['failed_files'].append({
            'pdf_id': pdf_id,
            'error': error,
            'timestamp': datetime.now().isoformat()
        })
        self.progress['failed_count'] += 1
        self.save_progress()
    
    def get_resume_info(self) -> str:
        """获取续传信息"""
        processed = len(self.progress['processed_files'])
        total = self.progress.get('total_files', 0)
        if total == 0:
            return "开始新的处理任务"
        percentage = (processed / total) * 100 if total > 0 else 0
        return f"已处理 {processed}/{total} 个文件 ({percentage:.1f}%)"
    
    def reset(self):
        """重置进度"""
        self.progress = {
            'processed_files': set(),
            'failed_files': [],
            'success_count': 0,
            'failed_count': 0,
            'start_time': datetime.now().isoformat(),
            'last_update': None,
            'total_files': 0
        }
        if self.progress_file.exists():
            self.progress_file.unlink()
        if self.state_file.exists():
            self.state_file.unlink()
        print("✅ 进度已重置")


def get_processed_files(output_folder: str) -> Set[str]:
    """从输出文件夹中获取已处理的PDF文件列表（通过检查输出文件）"""
    output_path = Path(output_folder)
    if not output_path.exists():
        return set()
    
    processed = set()
    for txt_file in output_path.glob("*.txt"):
        # 文件名（不含扩展名）就是PDF ID
        processed.add(txt_file.stem)
    
    return processed


# --- Batch Processing Function ---
def batch_process_pdfs(input_folder: str, output_folder: str, clean_start: bool = False, 
                      save_interval: int = 10):
    """Batch process all PDF files in the input folder with resume support."""
    input_path = Path(input_folder)
    output_path = Path(output_folder)
    
    # Check if input folder exists
    if not input_path.exists():
        print(f"Error: Input folder '{input_folder}' does not exist.")
        return
    
    # Create output folder if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)
    print(f"Output folder: {output_path.absolute()}")
    
    # Initialize progress tracker
    progress_tracker = ProcessingProgress(output_folder)
    
    # Clean start option
    if clean_start:
        progress_tracker.reset()
        print("🔄 使用 --clean-start 选项，将重新处理所有文件")
    
    # Get all PDF files
    pdf_files = sorted(input_path.glob("*.pdf"))
    
    if not pdf_files:
        print(f"No PDF files found in '{input_folder}'.")
        return
    
    # Update total files count
    progress_tracker.progress['total_files'] = len(pdf_files)
    
    # Get already processed files from output folder (for resume)
    if not clean_start:
        processed_from_output = get_processed_files(output_folder)
        # Merge with progress file data
        progress_tracker.progress['processed_files'].update(processed_from_output)
        progress_tracker.progress['success_count'] = len(processed_from_output)
    
    print(f"\n{'='*60}")
    print(f"📊 {progress_tracker.get_resume_info()}")
    print(f"{'='*60}")
    
    # Filter out already processed files
    remaining_files = [
        pdf_file for pdf_file in pdf_files 
        if pdf_file.stem not in progress_tracker.progress['processed_files']
    ]
    
    if not remaining_files:
        print("\n✅ 所有PDF文件已处理完成！")
        return
    
    print(f"\n找到 {len(pdf_files)} 个PDF文件，其中 {len(remaining_files)} 个待处理")
    print(f"已跳过 {len(pdf_files) - len(remaining_files)} 个已处理的文件\n")
    print("=" * 60)
    
    # Process remaining PDFs
    success_count = progress_tracker.progress['success_count']
    failed_files = progress_tracker.progress['failed_files'].copy()
    
    for idx, pdf_file in enumerate(remaining_files, 1):
        pdf_id = pdf_file.stem  # Get filename without extension
        output_file = output_path / f"{pdf_id}.txt"
        
        current_index = len(pdf_files) - len(remaining_files) + idx
        print(f"\n[{current_index}/{len(pdf_files)}] Processing: {pdf_file.name}")
        print(f"  PDF ID: {pdf_id}")
        
        try:
            # Process the PDF
            final_text = process_pdf_and_extract_text(str(pdf_file))
            
            # Save the extracted text
            output_file.write_text(final_text, encoding='utf-8')
            print(f"  ✓ Success! Saved to: {output_file.name}")
            
            # Mark as processed
            progress_tracker.mark_processed(pdf_id, success=True)
            success_count += 1
            
            # Save progress periodically
            if idx % save_interval == 0:
                print(f"  💾 Progress saved ({idx}/{len(remaining_files)} processed)")
            
        except Exception as e:
            error_msg = str(e)
            print(f"  ✗ Failed: {error_msg}")
            
            # Mark as failed
            progress_tracker.mark_failed(pdf_id, error_msg)
            failed_files.append({
                'pdf_id': pdf_id,
                'filename': pdf_file.name,
                'error': error_msg
            })
    
    # Final progress save
    progress_tracker.save_progress()
    
    # Print summary
    print("\n" + "=" * 60)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 60)
    print(f"Total files: {len(pdf_files)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {len(failed_files)}")
    
    if failed_files:
        print("\nFailed files:")
        for failed_info in failed_files[-10:]:  # Show last 10 failed files
            if isinstance(failed_info, dict):
                print(f"  - {failed_info.get('filename', failed_info.get('pdf_id', 'Unknown'))}: {failed_info.get('error', 'Unknown error')}")
            else:
                print(f"  - {failed_info}")
        
        if len(failed_files) > 10:
            print(f"  ... and {len(failed_files) - 10} more (see progress.json for details)")
    
    print(f"\n💾 进度已保存到: {progress_tracker.progress_dir}")

# --- Main Program Entry ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="PDF Full-Text Extractor - Batch Processing Version",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default folders (pdfs/ -> extracted_contents/)
  python process_pdf_fully.py
  
  # Specify custom input folder
  python process_pdf_fully.py --input /path/to/pdfs
  
  # Specify both input and output folders
  python process_pdf_fully.py --input /path/to/pdfs --output /path/to/output
        """
    )
    
    parser.add_argument(
        '--input',
        type=str,
        default='pdfs',
        help='Input folder containing PDF files (default: pdfs)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='extracted_contents',
        help='Output folder for extracted text files (default: extracted_contents)'
    )
    
    parser.add_argument(
        '--clean-start',
        action='store_true',
        help='Ignore existing progress and reprocess all files (default: resume from last checkpoint)'
    )
    
    parser.add_argument(
        '--save-interval',
        type=int,
        default=10,
        help='Save progress every N files processed (default: 10)'
    )
    
    args = parser.parse_args()
    
    print("PDF Full-Text Extractor (Batch Processing Version with Resume Support)")
    print("=" * 60)
    print(f"Input folder: {Path(args.input).absolute()}")
    print(f"Output folder: {Path(args.output).absolute()}")
    if args.clean_start:
        print("⚠️  Clean start mode: will reprocess all files")
    else:
        print("📂 Resume mode: will skip already processed files")
    print("=" * 60)
    
    # Start batch processing
    batch_process_pdfs(
        args.input, 
        args.output, 
        clean_start=args.clean_start,
        save_interval=args.save_interval
    )
