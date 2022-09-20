function M = GetEulerMatrix(roll, pitch, yaw) 
% GetEulerMatrix - ����ת�ǻ����ת����
% --------------
%   �õ�ŷ������ת��˳��Ϊyaw -> pitch -> roll
%   ��3x1���� V����ת��ϵΪ V2 = M x V
% 
% 
% Syntax
% ------
%   M = GetEulerMatrix(roll, pitch, yaw)
% 
% 
% Input Arguments
% ---------------
%   roll           - ��X����ת��(�Ƕ���)
%   pitch          - ��Y����ת��(�Ƕ���)
%   yaw            - ��Z����ת��(�Ƕ���)
%
% 
% Output Arguments
% ----------------
%   M              - ��ת����
%   
%
% GuanXiongJun , 2021-01-22

roll = roll * pi / 180;
pitch = pitch * pi / 180;
yaw = yaw * pi / 180;

Mx = [1 0 0;0 cos(pitch) -sin(pitch);0 sin(pitch) cos(pitch)];
My = [cos(roll) 0 sin(roll); 0 1 0; -sin(roll) 0 cos(roll)];
Mz = [cos(yaw) -sin(yaw) 0;sin(yaw) cos(yaw) 0;0 0 1];

M = My * Mx * Mz;

end