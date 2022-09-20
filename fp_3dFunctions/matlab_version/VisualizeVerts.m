function [img, img_pos, img_vec, pre_mask, varargout] = VisualizeVerts(verts, surface_depth, gridlen, edge, varargin)
% VisualizeObjectPoints  - ���ƿ��ӻ�
% ---------------------
%   �� XOY ƽ��� -Z �ӽ�ͶӰ���ӻ�����(ͼƬ����ֱ��ӦX��-Y)
%   ����ͼ���еĿն����������ֵ���
%
%
% Syntax
% ------
%   [img, img_pos, img_vec, pre_mask] = VisualizeObjectPoints(verts, surface_depth, gridlen, edge)
%   ���ӻ�����
%
%   [img, img_pos, img_vec, pre_mask, img_pos_gt] = VisualizeObjectPoints(verts, surface_depth, gridlen, edge��verts_gt)
%   ���ӻ�����,�� verts_gt ��Ϊ����ͼ��Ӧ����ά��ֵ
%
%   [img, img_pos, img_vec, pre_mask] = VisualizeObjectPoints(verts, surface_depth, gridlen, edge, col, row, size_c, size_r);
%   ָ��������ÿ������ͼƬ��λ�ã�ʹ����׼�ĵ����ڿ��ӻ�ͼƬ��Ҳ��һһ��Ӧ
%
%
% Examples
% --------
%   ������Ե�������ͼƬ������ͼƬ�Ե�����һһ��Ӧ
%     grid_verts1 = round(round(match_verts1 / gridlen) + 0.1); % ��ֹ-0�ĳ���
%     grid_verts2 = round(round(match_verts2 / gridlen) + 0.1);
%     grid_verts = [grid_verts1;grid_verts2];
%     min_col = min(grid_verts(:, 1));
%     min_row = min(grid_verts(:, 2));
%     max_col = max(grid_verts(:, 1)) - min_col + 2 * edge;
%     max_row = max(grid_verts(:, 2)) - min_row + 2 * edge;
%     col1 = grid_verts1(:, 1) - min_col + edge;
%     row1 = grid_verts1(:, 2) - min_row + edge;
%     col2 = grid_verts2(:, 1) - min_col + edge;
%     row2 = grid_verts2(:, 2) - min_row + edge;
%     [img1, img_pos1, img_vec1, pre_mask1] = VisualizeObjectPoints(match_verts1, surface_depth1, gridlen, edge, col1, row1, max_col, max_row);
%     [img2, img_pos2, img_vec2, pre_mask2] = VisualizeObjectPoints(match_verts2, surface_depth2, gridlen, edge, col2, row2, max_col, max_row);
%
%
% Input Arguments
% ---------------
%   verts           - ���� (Nx3)
%   surface_depth   - ÿ�����Ӧ�ı�����ȣ�Nx1
%   gridlen         - ��ɢ��ÿ�����ض�Ӧ�ĳ߶� (����ʹ�� 0.05)
%   edge            - ͼ��߽�Ŀհ� (����ʹ�� 30)
%   varargin        - ����������������ĵ��ƣ���Ҫ��ͼƬ��Ҳ������ʾʱ����ӵĶ������
%                   col             - ��ɢ���Ŀ��
%                   row             - ��ɢ���ĸ߶�
%                   size_c          - ͼ����
%                   size_r          - ͼ��߶�
%
%
% Output Arguments
% ----------------
%   img             - ���ӻ�ͼ��RxCx3
%   img_pos         - ���ӻ�ͼ����ÿһ���ص��Ӧ��λ�ã�RxCx3
%   img_vec         - ���ӻ�ͼ����ÿһ���Ӧ�ķ�������RxCx3
%   pre_mask        - ���ӻ�ͼ���ǰ������
%   img_pos_gt      - ϣ����Ӧ��ĳ������λ�ã�RxCx3
%
%
% GuanXiongJun , 2021-02-24

warning('off');


% ������
pc=pcdownsample(pointCloud(verts),'gridAverage',0.5); %0.5

% ʹ�� delaunayTriangulation ������������������ʷ�
DT = delaunayTriangulation(pc.Location);

% ���������ʷֵ����ɱ߽��棬��ʹ�������������ϴ�����ά�����ʷ�
[T,Xb] = freeBoundary(DT);
TR = triangulation(T,Xb);

% ���� TR ��ÿ������������ĺͶ���/�淨����
P = incenter(TR);
V = vertexNormal(TR);
F = faceNormal(TR);

% % ���ƿɼ����ֵ������ʷ��Լ����ĺ��淨��
% figure;
% trisurf(T,Xb(:,1),Xb(:,2),Xb(:,3),'FaceColor','cyan','FaceAlpha',0.8);
% axis equal; hold on;
% quiver3(P(:,1),P(:,2),P(:,3),F(:,1),F(:,2),F(:,3),0.5,'color','r');
% quiver3(Xb(:,1),Xb(:,2),Xb(:,3),V(:,1),V(:,2),V(:,3),0.5,'Color','b');

% ֻ���� -Z С�� 80 �ȵĵ�ɼ�
T = T(F(:,3)<-0.17,:);
V = V(unique(T(:)),:);
Xb = Xb(unique(T(:)),:);


% ��ֵ���ƿɼ�������ȣ��������Ƚ��Ƶĵ���Ϊ�ɼ���
F_Xb = scatteredInterpolant(Xb(:,1),Xb(:,2),Xb(:,3),'linear','none');
interpz = F_Xb(verts(:,1),verts(:,2));
F_V1 = scatteredInterpolant(Xb(:,1),Xb(:,2),V(:,1),'linear','none');
F_V2 = scatteredInterpolant(Xb(:,1),Xb(:,2),V(:,2),'linear','none');
F_V3 = scatteredInterpolant(Xb(:,1),Xb(:,2),V(:,3),'linear','none');
interpv = [F_V1(verts(:,1),verts(:,2)),F_V2(verts(:,1),verts(:,2)),F_V3(verts(:,1),verts(:,2))];

visibility = (abs(interpz - verts(:,3)) < 2.5);


% ֻʹ�ÿɼ�����
verts = verts(visibility,:);
% normal_vec = normal_vec(visibility, :);
surface_depth = surface_depth(visibility, :);
interpv = interpv(visibility, :);

% ͼ�������ʼ��
if nargin == 4
    grid_verts = round(round(verts / gridlen) + 0.1);
    col = grid_verts(:, 1) - min(grid_verts(:, 1)) + edge;
    row = grid_verts(:, 2) - min(grid_verts(:, 2)) + edge;
    size_c = max(col) + edge;
    size_r = max(row) + edge;
elseif nargin == 5
    verts_gt = varargin{1}(visibility,:);
    grid_verts = round(round(verts / gridlen) + 0.1);
    col = grid_verts(:, 1) - min(grid_verts(:, 1)) + edge;
    row = grid_verts(:, 2) - min(grid_verts(:, 2)) + edge;
    size_c = max(col) + edge;
    size_r = max(row) + edge;
else
    col = varargin{1}(visibility);
    row = varargin{2}(visibility);
    size_c = varargin{3};
    size_r = varargin{4};
end

% ��ֵ�õ�ƽ����ӻ�ֵ
[mx,my]=meshgrid(1:size_c,1:size_r);
F = scatteredInterpolant(col,row,surface_depth,'linear','none');
img_arr = F(mx,my);

F_P1 = scatteredInterpolant(col,row,verts(:,1),'linear','none');
F_P2 = scatteredInterpolant(col,row,verts(:,2),'linear','none');
F_P3 = scatteredInterpolant(col,row,verts(:,3),'linear','none');
img_pos = cat(3,F_P1(mx,my),F_P2(mx,my),F_P3(mx,my));

if nargin == 5
    F_PGT1 = scatteredInterpolant(col,row,verts_gt(:,1),'linear','none');
    F_PGT2 = scatteredInterpolant(col,row,verts_gt(:,2),'linear','none');
    F_PGT3 = scatteredInterpolant(col,row,verts_gt(:,3),'linear','none');
    varargout{1} = cat(3,F_PGT1(mx,my),F_PGT2(mx,my),F_PGT3(mx,my));
end

F_V1 = scatteredInterpolant(col,row,interpv(:,1),'linear','none');
F_V2 = scatteredInterpolant(col,row,interpv(:,2),'linear','none');
F_V3 = scatteredInterpolant(col,row,interpv(:,3),'linear','none');
img_vec = cat(3,F_V1(mx,my),F_V2(mx,my),F_V3(mx,my));


% ͼ��ǰ������
pre_mask = ~isnan(img_arr);

% ���ӻ�ͼ���һ��������ָ�Ƽ����ǽӴ���λ���Ϊ��ɫ���ǽӴ�ָ�����ڹ��յ��¼��߸���
img_max = max(img_arr(pre_mask));
img_min = min(img_arr(pre_mask));
img_arr = round((1 - ((img_arr - img_min) / (img_max - img_min))) * 255);
img_data = img_arr(pre_mask);
img_arr(~pre_mask) = 255;
img_arr(img_arr == 0) = 1;


% ֱ��ͼ����
hist_mask = hist(img_data,1:256);
cdf = cumsum(hist_mask);
cdf = (cdf - cdf(1)) * 255 / (cdf(end) - 1);
cdf = round(cdf / max(cdf) * 255);
img = cdf(img_arr)/255;

img = uint8(img*255);

end
