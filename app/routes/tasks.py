from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services import tasks as task_service

router = APIRouter()


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    task_data: TaskCreate, db: Session = Depends(get_db)
) -> TaskRead:
    return task_service.create_task(db, task_data)


@router.get("", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)) -> list[TaskRead]:
    return task_service.list_tasks(db)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: int = Path(gt=0), db: Session = Depends(get_db)
) -> TaskRead:
    task = task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=TaskRead)
def update_task(
    task_data: TaskUpdate,
    task_id: int = Path(gt=0),
    db: Session = Depends(get_db),
) -> TaskRead:
    task = task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task_service.update_task(db, task, task_data)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int = Path(gt=0), db: Session = Depends(get_db)
) -> Response:
    task = task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    task_service.delete_task(db, task)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
