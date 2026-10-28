from __future__ import annotations
import math
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
Matrix = list[list[float]]

def rigid_matrix(value: Matrix) -> Matrix:
    if len(value)!=4 or any(len(row)!=4 for row in value):
        raise ValueError("Transform must be a 4x4 matrix")
    if any(not math.isfinite(x) for row in value for x in row):
        raise ValueError("Transform must contain finite numbers")
    if any(abs(value[3][i]-[0,0,0,1][i])>1e-8 for i in range(4)):
        raise ValueError("Transform bottom row must be [0,0,0,1]")
    for i in range(3):
        for j in range(3):
            if abs(sum(value[k][i]*value[k][j] for k in range(3))-(1 if i==j else 0))>1e-5:
                raise ValueError("Transform rotation must be orthonormal; scaling is not permitted")
    r=value
    det=r[0][0]*(r[1][1]*r[2][2]-r[1][2]*r[2][1])-r[0][1]*(r[1][0]*r[2][2]-r[1][2]*r[2][0])+r[0][2]*(r[1][0]*r[2][1]-r[1][1]*r[2][0])
    if abs(det-1)>1e-5:raise ValueError("Transform rotation determinant must be +1")
    return value

class StrictModel(BaseModel):
    model_config=ConfigDict(extra="forbid",allow_inf_nan=False,strict=True)

class UVBounds(StrictModel):
    u_min_mm: float
    u_max_mm: float
    v_min_mm: float
    v_max_mm: float
    @model_validator(mode="after")
    def ordered(self):
        if self.u_min_mm>=self.u_max_mm or self.v_min_mm>=self.v_max_mm:
            raise ValueError("UV minima must be smaller than maxima")
        return self

class Target(StrictModel):
    asset_id: Identifier = "demo_car_4500"
    units: Literal["mm"] = "mm"
    region_uv_mm: UVBounds | None = None
    T_robot_base_workpiece: Matrix | None = None
    @field_validator("T_robot_base_workpiece")
    @classmethod
    def transform(cls,value):return rigid_matrix(value) if value is not None else value

class Robot(StrictModel):
    model_id: Identifier = "huayan_e12"
    tool_id: Literal["spray_tcp_200"] = "spray_tcp_200"

class Process(StrictModel):
    standoff_mm: float = Field(default=200,ge=100,le=350)
    speed_mm_s: float = Field(default=400,ge=50,le=700)
    spray_width_mm: float = Field(default=240,ge=60,le=400)
    overlap_ratio: float = Field(default=0.5833333333333333,ge=0,le=0.9)
    passes: int = Field(default=1,ge=1,le=3)
    @model_validator(mode="after")
    def spacing(self):
        if self.spray_width_mm*(1-self.overlap_ratio)<10:
            raise ValueError("Derived spray row spacing must be at least 10 mm")
        return self

class Planning(StrictModel):
    method: Literal["sac","raster"] = "sac"
    policy_id: Literal["sac_car_side_v1"] = "sac_car_side_v1"
    sample_step_mm: float = Field(default=40,ge=10,le=80)

class Execution(StrictModel):
    backend: Literal["mock","robodk"] = "mock"
    mode: Literal["plan_only","simulate"] = "plan_only"
    show_window: bool = False
    simulation_speed: float = Field(default=5,ge=0.1,le=20)
    timeout_s: float = Field(default=300,ge=5,le=900)

class TaskRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    task_id: Identifier
    skill_id: Literal["spray_surface.v1"] = "spray_surface.v1"
    target: Target = Field(default_factory=Target)
    robot: Robot = Field(default_factory=Robot)
    process: Process = Field(default_factory=Process)
    planning: Planning = Field(default_factory=Planning)
    execution: Execution = Field(default_factory=Execution)
    context: dict[str,str] = Field(default_factory=dict,max_length=16)

class AssetImport(StrictModel):
    asset_id: Identifier
    input_units: Literal["mm","m"]
    T_workpiece_input: Matrix
    T_robot_base_workpiece: Matrix
    region_uv_mm: UVBounds | None = None
    grid_mm: float = Field(default=15,ge=2,le=50)
    @field_validator("T_workpiece_input","T_robot_base_workpiece")
    @classmethod
    def transform(cls,value):return rigid_matrix(value)

TaskState=Literal['queued','planning','validating','simulating','succeeded','failed','cancelled']

class ErrorInfo(StrictModel):
    code:str
    message:str
    details:dict|list=Field(default_factory=dict)

class TaskEvent(StrictModel):
    sequence:int
    at:str
    state:TaskState
    progress:float
    message:str

class ValidationResult(StrictModel):
    passed:bool
    reachable:bool|None
    collision_free:bool|None
    executable:bool
    scope:str
    sampling_mm:float|None=None
    sampling_deg:float|None=None
    method:str|None=None

class QualityMetrics(StrictModel):
    coverage_fraction:float
    relative_dose_mean:float
    relative_dose_cv:float
    estimated_spray_seconds:float
    evaluated_area_mm2:float
    model:str
    physical_thickness_um:float|None
    scope:str

class ExecutionResult(StrictModel):
    requested:bool
    completed:bool
    executed_in_simulator:bool
    waypoints_executed:int
    maximum_tcp_position_error_mm:float|None=None
    paint_layers:int|None=None

class TaskResult(StrictModel):
    schema_version:Literal['1.0']
    task_id:str
    backend:Literal['mock','robodk']
    mode:Literal['plan_only','simulate']
    simulation_only:Literal[True]
    robot_id:str
    asset_id:str
    planner:str
    region_uv_mm:UVBounds
    waypoint_count:int
    trajectory_url:str
    runtime_s:float
    validation:ValidationResult
    quality:QualityMetrics|None
    execution:ExecutionResult
    warnings:list[str]
    units:dict[str,str]
    simulator_version:str|None=None
    T_robot_base_workpiece:Matrix|None=None

class TaskStatus(StrictModel):
    schema_version:Literal['1.0']
    task_id:str
    state:TaskState
    progress:float
    message:str
    created_at:str
    updated_at:str
    request_sha256:str
    context:dict[str,str]
    result:TaskResult|None
    error:ErrorInfo|None
    events:list[TaskEvent]

class TaskAccepted(TaskStatus):
    status_url:str
